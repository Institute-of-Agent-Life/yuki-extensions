"""Original-Bot Telegram file delivery; separate platform proof from Host authorization."""
import hashlib
import json
import os
import sys
from package import build


def prepare(root, output):
    sys.path.insert(0,str(root / 'tests/peers'))
    from telegram_media_wire import exercise
    package = build(root, 'telegram', output/'packages')
    name = 'yuki-telegram' + ('.exe' if os.name == 'nt' else '')
    result = exercise(output/'packages'/name,output/'work')
    (output/'wire.json').write_text(json.dumps(result.pop('wire'),indent=2)+'\n',encoding='utf-8')
    pin = json.loads((root/package['source']['sdk_contract']).read_bytes())
    # Bind this receipt to the inputs actually used by the Windows package builder.
    paths = [root/'catalog/telegram.json',root/package['source']['sdk_contract'],
             root/'ci/package.py',root/'ci/handshake_cargo.py',root/'ci/check.py',
             root/'tests/cases/EXT-004.py',root/'tests/peers/telegram_media_wire.py',
             *(root/'plugins/telegram').glob('*'),*(root/'plugins/telegram/src').glob('*.rs')]
    result.update(plugin_sha256=package['artifacts'][name],sdk_sha256=pin['rust_crate_sha256'],
                  sdk_version=pin['sdk']['rust'],sdk_source=pin['source_commit'],
                  source_bindings={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in paths if p.is_file() and not p.name.startswith('._')},
                  card_status="PLATFORM_MEDIA_VERIFIED_HOST_AUTHORIZATION_AND_SOCIAL_PENDING")
    (output/'build-receipt.json').write_text(json.dumps(package,indent=2)+'\n',encoding='utf-8')
    return 'telegram-delivery.json',result


def run(root, output):
    from telegram_outbound_check import run as check_original_delivery
    return 'telegram-delivery.json', check_original_delivery(root, output / 'native')
