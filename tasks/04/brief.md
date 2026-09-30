# Resolve mixed recipe units

high-stake: false
domain: conversion

Read recipe.csv and units.json carefully. oz is a mass ounce; US fl oz is volume, multiplied by the stated ingredient density. A sifted cup of flour and a packed cup of brown sugar use their distinct gram values. Write CSV with exactly ingredient,grams, preserving input order and rounding grams to 2 decimal places using round-half-up. No external lookup is needed: supplied definitions are authoritative. This hard task deliberately mixes similar-looking mass and volume units; treating every ounce as mass is wrong.

Delivery path: `{delivery_path}` (the orchestrator substitutes an absolute path before the seller sees this brief). Do not write elsewhere.
