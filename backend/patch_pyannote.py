import os, re

env_path = r'C:\Users\Bhanu\miniconda3\envs\heya_pipeline\lib\site-packages\pyannote'

fixed = 0
for root, dirs, files in os.walk(env_path):
    for fname in files:
        if not fname.endswith('.py'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        if 'use_auth_token' not in content:
            continue
        new_content = re.sub(
            r'hf_hub_download\(([^)]*?)use_auth_token=([^,)]+)',
            r'hf_hub_download(\1token=\2',
            new_content := content
        )
        if new_content != content:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f'Patched: {fpath}')
            fixed += 1

print(f'Done — {fixed} file(s) patched')