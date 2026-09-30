#!/usr/bin/env python3
"""run.sh implementation: external orchestration; agents never call the notary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from protocol import parse_block
from notary import read_entries
from referral import handoff_digest, mediated_brief, referral_reliability

ROOT = Path(__file__).resolve().parent


def timeout_for(configured, provider):
    return 300 if provider == 'ollama' else configured


class TurnFailed(ValueError):
    pass


class IntegrityFailure(RuntimeError):
    pass


class Runner:
    def __init__(self, args):
        self.args = args
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.label):
            raise ValueError('label must use only letters, numbers, dots, underscores, hyphens')
        if args.task_id not in ('01','02','03','04'):
            raise ValueError('task_id must be 01, 02, 03, or 04')
        provider = os.environ.get('SR_MODEL_PROVIDER', 'openai').lower()
        if not args.mock and provider not in ('openai', 'ollama'):
            raise ValueError('SR_MODEL_PROVIDER must be openai or ollama')
        if not args.mock and provider == 'openai' and not os.environ.get('OPENAI_API_KEY'):
            raise ValueError('OPENAI_API_KEY is required for non-mock model execution')
        self.config = json.loads((ROOT/'config.json').read_text())
        self.task_dir = ROOT/'tasks'/args.task_id
        self.task = json.loads((self.task_dir/'task.json').read_text())
        self.run_dir = ROOT/'runs'/args.label
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.env = dict(os.environ)
        self.env.pop('NOTARY_CALLER', None)
        self.env['SR_TASK_ID'] = args.task_id
        if args.mediated:
            self.env['SR_REFERRAL'] = 'referral-agent-1'
        self.audit_findings = []
        self.events = []
        self.team_debates = []
        self.live = args.live
        self.serial = 0
        self.metrics = {'task_id':args.task_id, 'mode':'baseline' if args.baseline else 'improved',
                        'bad_deliveries':0, 'retries':0, 'ask_human':0, 'agent_calls':0,
                        'attempts':0, 'status':'running', 'forced_seller':os.environ.get('SR_FORCE_SELLER'),
                        'team_member_calls':0,
                        'execution_mode':'deterministic-mock' if args.mock else 'hybrid-live-model',
                        'model_provider':None if args.mock else provider,
                        'model_calls':0, 'model_input_tokens':0, 'model_output_tokens':0,
                        'model_names':[]}
        if args.mediated:
            self.metrics['referral'] = 'referral-agent-1'

    def log(self, message):
        self.events.append(message)
        (self.run_dir/'timeline.md').write_text('# Run '+self.args.label+'\n\n'+'\n'.join(f'{i}. {event}' for i,event in enumerate(self.events,1))+'\n')
        if self.live:
            print('[live] '+message, flush=True)

    def command(self, command, *, env=None, cwd=None, stdin=None):
        return subprocess.run(command, input=stdin, text=True, capture_output=True,
                              cwd=cwd or ROOT, env=env or self.env,
                              timeout=timeout_for(self.config['agent_timeout_seconds'],
                                                  self.env.get('SR_MODEL_PROVIDER', 'openai')))

    def audit(self, mode, *args, expected_fabrication=False):
        proc = self.command([sys.executable,str(ROOT/'audit.py'),mode,*map(str,args)])
        message = proc.stdout + proc.stderr
        with (self.run_dir/'audit.txt').open('a') as f:
            f.write(f'[{mode}] '+message)
        if proc.returncode:
            self.audit_findings.append(message.strip())
            confirmed = (expected_fabrication and "fabrication flag notarised" in proc.stdout
                         and any(e.get("kind") == "flag" and e.get("type") == "fabrication"
                                 and e.get("task_run_id") == str(args[0]) for e in read_entries()))
            if not confirmed:
                raise IntegrityFailure(message)
        if self.live:
            print('[live] audit '+mode, flush=True)
        return proc.returncode

    def notarise(self, kind, payload):
        proc = self.command([sys.executable,str(ROOT/'notary.py'),kind,json.dumps(payload)])
        with (self.run_dir/'notary.txt').open('a') as f:
            f.write(kind+' '+json.dumps(payload)+'\n'+proc.stdout+proc.stderr)
        if proc.returncode:
            raise IntegrityFailure('notary refused '+kind+': '+proc.stderr)
        self.log('Notary appended '+kind+' for '+payload['task_run_id']+'.')

    def lookup(self):
        proc = self.command([sys.executable,str(ROOT/'engine.py'),'lookup',self.task['domain']])
        if proc.returncode:
            raise IntegrityFailure('lookup failed: '+proc.stderr)
        return json.loads(proc.stdout)

    def turn(self, role, phase, context, workdir, delivery=None):
        self.serial += 1
        stem = f'{self.serial:02d}-{role}-{phase}'
        prefix = self.run_dir/stem
        # Persist the exact visible context, separate from orchestration-only state.
        prefix.with_suffix('.input.json').write_text(json.dumps(context,indent=2)+'\n')
        prompt_parts = []
        names = ['buyer.md'] if role in ('buyer', 'referral') else ['seller-common.md',role+'.md']
        for name in names:
            path = ROOT/'agents/prompts'/name
            if path.exists():
                prompt_parts.append(path.read_text())
        prompt_parts.append('CURRENT PHASE: '+phase)
        if phase == 'commit':
            prompt_parts.append('For THIS turn return ONLY the commit block. Do not create the delivery yet. The notary must record your commitment before work starts.')
        elif phase == 'delivery':
            prompt_parts.append('Your commitment was notarised in the previous turn. Perform the work now and return ONLY the delivery block. Do not emit a new commitment.')
        prompt_parts.append(json.dumps(context,indent=2))
        prompt = prefix.with_suffix('.prompt.md')
        prompt.write_text('\n\n'.join(prompt_parts))
        snapshot = prefix.with_suffix('.custody.json')
        self.audit('before', snapshot)
        env = dict(self.env)
        env.pop('SR_RECORDS_DIR',None)
        env.pop('SR_FORCE_SELLER',None)
        env['SR_PHASE'] = phase
        if delivery:
            env['SR_DELIVERY_PATH'] = str(delivery)
            env['SR_TASK_DIR'] = str(workdir)
        if self.args.mock:
            script = 'mock_referral.py' if role == 'referral' else ('mock_buyer.py' if role == 'buyer' else 'mock_seller.py')
            cmd = [sys.executable, str(ROOT/'agents'/script)]
            if role not in ('buyer', 'referral'):
                cmd += [role, self.args.task_id]
        else:
            cmd = ['bash',str(ROOT/'agents/call_agent.sh'),role,str(prompt),str(workdir)]
        self.metrics['agent_calls'] += 1
        try:
            proc = self.command(cmd,env=env,cwd=workdir,stdin=json.dumps(context))
            output, errors, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or b''
            errors = 'agent timed out'
            output = output.decode(errors='replace') if isinstance(output,bytes) else output
            code = 124
        prefix.with_suffix('.output.txt').write_text(output)
        prefix.with_suffix('.stderr.txt').write_text(errors)
        self.audit('after', snapshot)
        self.log(f'{stem}: agent exit {code}; transcript `{stem}.output.txt`.')
        if code:
            if not self.args.mock and code == 2 and 'not implemented' in output:
                raise NotImplementedError('real agent adapter: not implemented')
            raise TurnFailed(f'{stem}: agent exited {code}: {errors}')
        try:
            parsed = parse_block(output, phase)
            if self.live and role == 'referral' and phase == 'choice':
                print('[live] referral team completed: 4 roles and Lead synthesis', flush=True)
            if self.live and role not in ('buyer', 'referral') and phase == 'delivery':
                print(f'[live] {role} delivery returned; checker will verify it', flush=True)
            return parsed
        except ValueError as exc:
            raise TurnFailed(f'{stem}: {exc}') from exc

    def ask_human(self, reason):
        payload = {'task_run_id':self.args.label+':human','buyer':'project-manager' if self.args.mediated else 'buyer','action':'ask_human','reason':reason}
        if self.args.mediated:
            payload['referral'] = 'referral-agent-1'
        self.notarise('choice', payload)
        self.metrics['ask_human'] = 1
        self.metrics['status'] = 'ask_human'
        self.log('Ask human: '+reason)

    def execute(self):
        initial = self.run_dir/'initial.custody.json'
        self.audit('before',initial)
        self.log('Mode '+self.metrics['mode']+'; task '+self.args.task_id+'.')
        if self.task['high_stake']:
            self.ask_human('Task is marked high-stake.')
            self.audit('verify',initial)
            return
        available = list(self.config['sellers'])
        for attempt in range(self.config['max_retries']+1):
            if not available:
                break
            if attempt:
                self.metrics['retries'] += 1
            transaction = f'{self.args.label}:attempt-{attempt+1}'
            context = {'phase':'choice','domain':self.task['domain'], 'available':available,
                       'mode':self.metrics['mode'], 'high_stake':self.task['high_stake'],
                       'human_threshold':self.config['human_threshold'],
                       'brief':(self.task_dir/'brief.md').read_text()}
            if self.args.mediated:
                context.update({'channel':'referral','project_manager':'project-manager',
                                'team_trace_path':str(self.run_dir/f'team-debate-attempt-{attempt+1}.json')})
            scores = self.lookup()
            if all(scores[s]['character'] < self.config['human_threshold'] for s in available):
                self.ask_human('Every remaining candidate is below the character threshold.')
                break
            if self.args.baseline:
                context['self_descriptions'] = (ROOT/'agents/self_descriptions.md').read_text()
            else:
                context['lookup'] = scores
            forced = self.metrics['forced_seller'] if attempt == 0 else None
            if forced:
                if forced not in available:
                    raise ValueError('unknown forced seller')
                context['forced_seller'] = forced
            choice_role = 'referral' if self.args.mediated else 'buyer'
            buyer_dir = self.run_dir/('referral' if self.args.mediated else 'buyer')
            buyer_dir.mkdir(exist_ok=True)
            try:
                choice = self.turn(choice_role,'choice',context,buyer_dir)
                if self.args.mediated and choice.get('team_trace') is not False:
                    self.metrics['team_member_calls'] = 4
                    trace_path = Path(context['team_trace_path'])
                    if trace_path.exists():
                        self.team_debates.append(json.loads(trace_path.read_text()))
                if choice.get('action') == 'ask_human':
                    self.ask_human(choice['reason'])
                    break
                seller = choice['seller']
                if seller not in available:
                    raise TurnFailed('buyer selected an unavailable seller')
            except TurnFailed as exc:
                self.log('Choice failed: '+str(exc))
                continue
            available.remove(seller)
            self.metrics['attempts'] += 1
            common = {'task_run_id':transaction,'buyer':'project-manager' if self.args.mediated else 'buyer','seller':seller,'domain':self.task['domain']}
            if self.args.mediated:
                common['referral'] = 'referral-agent-1'
            choice_payload = {**common,'reason':choice['reason']}
            if self.args.mediated:
                choice_payload['confidence'] = choice.get('confidence', 0.5)
                choice_payload['dissent'] = choice.get('dissent', [])
                debate = self.team_debates[-1] if self.team_debates else {}
                lead = debate.get('lead', {})
                choice_payload['decision_factors'] = lead.get('decision_factors', [])
                choice_payload['confidence_calculation'] = lead.get('confidence_calculation', {})
            self.notarise('choice', choice_payload)
            workdir = self.run_dir/f'attempt-{attempt+1}'/seller
            workdir.mkdir(parents=True)
            for source in self.task_dir.iterdir():
                if source.is_file() and source.name not in ('check.py','brief.md'):
                    shutil.copy2(source,workdir/source.name)
            delivery = workdir/self.task['delivery_name']
            brief = (self.task_dir/'brief.md').read_text()
            if self.args.mediated:
                brief = mediated_brief(brief)
            brief = brief.replace('{delivery_path}',str(delivery))
            handoff_sha256 = handoff_digest(brief)
            if self.args.mediated:
                self.env['SR_HANDOFF_SHA256'] = handoff_sha256
            (workdir/'brief.md').write_text(brief)
            seller_context = {'phase':'commit','brief':brief,'input_directory':str(workdir),'delivery_path':str(delivery)}
            if self.args.mediated:
                seller_context.update({'channel':'referral','referral':'referral-agent-1','handoff_sha256':handoff_sha256})
            try:
                commitment = self.turn(seller,'commit',seller_context,workdir,delivery)
                if delivery.exists():
                    raise TurnFailed('seller wrote delivery before notarised commitment')
                # Only the contract's fields may enter trusted transaction metadata.
                self.notarise('commit',{**common,'claim':commitment['claim'],'confidence':commitment['confidence']})
                self.notarise('stake',{**common,'stake':self.config['default_stake']})
                seller_context.update(phase='delivery',commitment=commitment)
                claim = self.turn(seller,'delivery',seller_context,workdir,delivery)
                if Path(claim['path']) != delivery or delivery.is_symlink():
                    raise TurnFailed('delivery must be the assigned file, not a different path or symlink')
                delivery_payload = {**common,'path':claim['path'],'summary':claim['summary']}
                if self.args.mediated:
                    delivery_payload['handoff_sha256'] = handoff_sha256
                self.notarise('delivery', delivery_payload)
                flagged = self.audit('delivery',transaction,seller,common['buyer'],self.task['domain'],delivery,expected_fabrication=True)
                check = self.command([sys.executable,str(self.task_dir/'check.py'),str(delivery)])
                (workdir.parent/'check.txt').write_text(check.stdout+check.stderr)
                verdict = 'pass' if check.returncode == 0 and not flagged else 'fail'
                reason = (check.stdout+check.stderr).strip() or 'checker returned '+str(check.returncode)
                self.log(f'{seller}: check {verdict}; '+reason)
                # Freeze the actual artifact before buyer reporting; a buyer is a reader.
                evidence = hashlib.sha256(delivery.read_bytes() if delivery.is_file() else b'').hexdigest()
                outcome_context = {'phase':'outcome','delivery_claim':claim,'check_result':verdict,'check_reason':reason}
                if delivery.is_file():
                    outcome_context['delivered_content'] = delivery.read_text(errors='replace')
                outcome = self.turn(choice_role,'outcome',outcome_context,buyer_dir)
                after = hashlib.sha256(delivery.read_bytes() if delivery.is_file() else b'').hexdigest()
                if evidence != after:
                    raise IntegrityFailure('delivery changed during buyer review')
                if outcome['result'] != verdict:
                    raise TurnFailed('buyer outcome disagrees with authoritative checker')
                self.notarise('outcome',{**common,'result':outcome['result'],'note':outcome['note'],'evidence':'sha256:'+evidence})
                if self.args.mediated:
                    self.metrics['referral_reliability'] = referral_reliability(read_entries(), 'referral-agent-1')
                if verdict == 'pass':
                    self.metrics['status'] = 'pass'
                    break
                self.metrics['bad_deliveries'] += 1
            except TurnFailed as exc:
                self.metrics['bad_deliveries'] += 1
                self.log('Attempt failed: '+str(exc))
        if self.metrics['status'] == 'running':
            self.ask_human('No successful delivery within the retry limit.')
        self.audit('verify', initial)

    def finish(self):
        if self.args.mediated and self.team_debates:
            latest = self.team_debates[-1]
            aggregate = {**latest, 'attempts': self.team_debates}
            (self.run_dir/'team-debate.json').write_text(json.dumps(aggregate, indent=2)+'\n')
        model_calls = []
        for path in sorted(self.run_dir.glob('team-debate-attempt-*.json')):
            try:
                model_calls.extend(json.loads(path.read_text()).get('model_calls', []))
            except (OSError, ValueError):
                pass
        for path in sorted(self.run_dir.glob('*.model.json')):
            try:
                metadata = json.loads(path.read_text())
                if isinstance(metadata, dict):
                    model_calls.append(metadata)
            except (OSError, ValueError):
                pass
        self.metrics['model_calls'] = len(model_calls)
        self.metrics['model_input_tokens'] = sum(item.get('input_tokens', 0) for item in model_calls)
        self.metrics['model_output_tokens'] = sum(item.get('output_tokens', 0) for item in model_calls)
        self.metrics['model_names'] = sorted({item.get('model') for item in model_calls if item.get('model')})
        (self.run_dir/'metrics.json').write_text(json.dumps(self.metrics,indent=2)+'\n')
        with (self.run_dir/'audit.txt').open('a') as f:
            if self.audit_findings:
                f.write('AUDIT FAIL: '+'; '.join(s.replace('\n',' ') for s in self.audit_findings)+'\n')
            else:
                f.write('AUDIT PASS\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task_id'); parser.add_argument('label')
    parser.add_argument('--baseline',action='store_true'); parser.add_argument('--mock',action='store_true'); parser.add_argument('--mediated',action='store_true'); parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    runner=None
    code=0
    try:
        runner=Runner(args)
        runner.execute()
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc),file=sys.stderr)
        code=2
        if runner:
            runner.metrics['status']='error'
            runner.log('Run stopped: '+str(exc))
            if isinstance(exc,IntegrityFailure) and str(exc) not in runner.audit_findings:
                runner.audit_findings.append(str(exc))
    finally:
        if runner:
            runner.finish()
            print(json.dumps(runner.metrics))
    return code


if __name__ == '__main__':
    sys.exit(main())
