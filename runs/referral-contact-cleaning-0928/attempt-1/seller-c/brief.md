# Clean a contact table

high-stake: false
domain: data-cleaning

Read messy.csv. Rename columns to id,name,email,city in that order. Trim fields, collapse repeated whitespace in names and cities, lowercase emails, convert IDs to canonical integers. Keep the first occurrence of each numeric ID, drop later duplicates, sort by numeric ID. Preserve the case of names and cities. Write CSV, no index column.

Delivery path: `/Users/yvette/Code/service-record/runs/referral-contact-cleaning-0928/attempt-1/seller-c/delivery.csv` (the orchestrator substitutes an absolute path before the seller sees this brief). Do not write elsewhere.
