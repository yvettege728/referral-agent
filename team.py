"""Deterministic internal Referral Team: role opinions plus a lead synthesis."""

ROLE_ORDER = ('buyer_liaison', 'talent_scout', 'research_analyst', 'risk_partner')
ROLE_WEIGHTS = {'buyer_liaison': 0.15, 'talent_scout': 0.15, 'research_analyst': 0.30, 'risk_partner': 0.40}


def _score(scores, seller, domain):
    record = scores.get(seller, {})
    return (record.get('character', 0), record.get('professional', {}).get(domain, 0))


def _best(available, scores, domain, key):
    return max(available, key=lambda seller: (key(scores.get(seller, {}), domain), -available.index(seller)))


def opinion_for(role, context):
    available = list(context.get('available', []))
    domain = context.get('domain', '')
    scores = context.get('lookup', {})
    if context.get('mode') == 'baseline':
        scores = {seller: {'character': 40, 'professional': {domain: 50}} for seller in available}
    if role == 'buyer_liaison':
        return {
            'role': role, 'seller': None, 'confidence': 0.70,
            'rationale': 'Clarifies the buyer priority and keeps the referral promise realistic before selecting a seller.',
            'evidence': 'buyer brief and stated risk tolerance', 'concern': 'A fast match may be a poor fit if the brief is ambiguous.'
        }
    if not available:
        return {'role': role, 'seller': None, 'confidence': 0.05, 'rationale': 'No candidates remain.', 'evidence': 'candidate list', 'concern': 'Escalate to a human.'}
    if role == 'talent_scout':
        seller = max(available, key=lambda name: (_score(scores, name, domain)[1], available.index(name)))
        rationale = 'Prioritizes domain performance and speed so the buyer gets a practical shortlist.'
        confidence = 0.78
    elif role == 'research_analyst':
        seller = max(available, key=lambda name: (_score(scores, name, domain)[0], _score(scores, name, domain)[1], -available.index(name)))
        rationale = 'Prioritizes durable evidence in the notarized record over a persuasive self-description.'
        confidence = 0.82
    elif role == 'risk_partner':
        seller = max(available, key=lambda name: (_score(scores, name, domain)[0], -_score(scores, name, domain)[1], -available.index(name)))
        rationale = 'Protects the referral reputation by avoiding weak-character candidates and overconfident promises.'
        confidence = round(max(0.55, min(0.90, _score(scores, seller, domain)[0] / 100)), 2)
    else:
        raise ValueError('unknown team role: '+role)
    character = _score(scores, seller, domain)[0]
    concern = 'Speed can hide evidence gaps.' if role == 'talent_scout' else 'The strongest record may not be the fastest match.'
    return {'role': role, 'seller': seller, 'confidence': confidence, 'rationale': rationale,
            'evidence': {'character': character, 'professional': _score(scores, seller, domain)[1]}, 'concern': concern}


def synthesize(opinions, context):
    available = list(context.get('available', []))
    valid = [item for item in opinions if item.get('seller') in available]
    weights = {**ROLE_WEIGHTS, **context.get('role_weights', {})}
    candidate_weights = {seller: 0.0 for seller in available}
    for item in valid:
        candidate_weights[item['seller']] += weights.get(item['role'], 0.0)
    selected_seller = max(available, key=lambda seller: (candidate_weights[seller], -available.index(seller)))
    lead_source = next(item for item in valid if item['seller'] == selected_seller)
    dissent = [
        {'role': item['role'], 'seller': item['seller'], 'reason': item['rationale']}
        for item in opinions if item.get('seller') and item.get('seller') != lead_source['seller']
    ]
    total_weight = sum(weights.get(item['role'], 0.0) for item in valid) or 1.0
    base_confidence = round(sum(item['confidence'] * weights.get(item['role'], 0.0) for item in valid) / total_weight, 2)
    dissent_penalty = round(0.04 * len(dissent), 2)
    final_confidence = min(0.90, max(0.55, round(base_confidence - dissent_penalty, 2)))
    decision_factors = [
        {'role': item['role'], 'seller': item.get('seller'), 'weight': weights.get(item['role'], 0.0),
         'used': item.get('seller') == lead_source.get('seller'), 'rationale': item['rationale']}
        for item in opinions
    ]
    return {'seller': lead_source['seller'], 'confidence': final_confidence,
            'reason': 'Lead Referral selected the highest weighted evidence-backed option after weighing buyer fit, speed, research, and risk.',
            'dissent': dissent, 'decision_factors': decision_factors,
            'confidence_calculation': {'base': base_confidence, 'dissent_penalty': dissent_penalty,
                                       'final': final_confidence}}


def run_team(context):
    opinions = [opinion_for(role, context) for role in ROLE_ORDER]
    return {'opinions': opinions, 'lead': synthesize(opinions, context)}
