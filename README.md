# music-files-reorganization
organize and identify mis-named songs from google takeout

setup:

python3 -m venv {{env_name}}

source {{env_name}}/bin/activate

pip install -r requirements.txt

## TODO

- get acoustid working - try direct http call to services since pyacoustid isn't playing nice.
- let it scan the entire library repeatedly, correcting matches along the way
  - working acoustid will help this where it can hopefully clean out the /unknown folder
- ability to identify possible mismatches
  - again, working acoustid could really help.
  - would need a .env setting to control mismatch remediation
    - mismatch remediation would make acoustid the priority for matching
      - if fingerprint doesn't match metadata, change to acoustid metadata and move to new location
      - use llm to decide whether the change is necessary?