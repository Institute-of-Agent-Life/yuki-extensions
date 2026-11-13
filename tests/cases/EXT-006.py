"""Verify original Feishu and Lark resources, delivery and owner disposition."""
from contextlib import nullcontext
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from package import build


def prepare(root,output):
    work=output/'work';work.mkdir()
    spec=importlib.util.spec_from_file_location('original_feishu_case',root/'tests/cases/EXT-005.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    Frame,serve=fixture.fixture_imports(root,work)
    from feishu_media_wire import one,cleanup_without_credentials
    package=build(root,'feishu',output/'packages')
    name='yuki-feishu'+('.exe' if os.name=='nt' else '')
    cleanup=cleanup_without_credentials(output/'packages'/name)
    rows=[one(output/'packages'/name,Frame,serve,domain,kind) for domain,kind in [('feishu','image'),('lark','file')]]
    assert rows[0]['sha256']!=rows[1]['sha256']
    for row in rows:(output/(row['domain']+'-wire.json')).write_text(json.dumps(row.pop('wire'),indent=2)+'\n',encoding='utf8')
    (output/'build-receipt.json').write_text(json.dumps(package,indent=2)+'\n',encoding='utf8')
    pin=json.loads((root/package['source']['sdk_contract']).read_bytes())
    paths=[root/'catalog/feishu.json',root/package['source']['sdk_contract'],root/'ci/package.py',
        root/'ci/handshake_cargo.py',root/'ci/check.py',root/'tests/cases/EXT-006.py',root/'tests/cases/EXT-005.py',
        *(root/'tests/peers'/n for n in ['feishu_media_wire.py','feishu_upload.py','feishu_mentions.py','lark_frames.py','lark-fixture.lock.json']),
        *(root/'plugins/feishu').glob('*'),*(root/'plugins/feishu/src').glob('*.rs')]
    return 'lark-rest.json',{'status':'PASS','card_status':'PLATFORM_RESOURCE_VERIFIED_HOST_AND_SOCIAL_PENDING',
        'actual_host_consumption':False,'models':0,'domains':rows,'erasure_only':cleanup,'binary_sha256':package['artifacts'][name],
        'sdk_source':pin['source_commit'],'sdk_sha256':pin['rust_crate_sha256'],'sdk_version':pin['sdk']['rust'],
        'source_bindings':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file() and not p.name.startswith('._')}}


def qualified_package(root, system, package):
    from feishu_release_check import TAG

    catalog = json.loads((root / 'catalog/verified.json').read_bytes())
    qualified = root / catalog[TAG]['qualification']
    publication = json.loads((root / 'artifacts/EXT-043/feishu-published-0.1.0/github-publication.json').read_bytes())
    qualification = qualified / 'extension-release-lock.json'
    assert publication['status'] == 'published-and-downloaded' and publication['tag'] == TAG
    assert hashlib.sha256(qualification.read_bytes()).hexdigest() == publication['qualification_sha256']
    registry = runpy.run_path(str(root / 'ci/publish-plugin.py'))
    registry['verify_qualification'](root, TAG)

    release = Path(os.environ['YUKI_FEISHU_RELEASE_ZIP']).resolve(strict=True)
    name = f'yuki-feishu-0.1.0-{system}.zip'
    asset, = (row for row in publication['assets'] if row['name'] == name)
    assert release.stat().st_size == asset['bytes']
    assert hashlib.sha256(release.read_bytes()).hexdigest() == asset['sha256']
    package.mkdir()
    with ZipFile(release) as archive, ZipFile(qualified / f'{system}.zip') as witness:
        manifest = archive.read('package-manifest.json')
        assert manifest == witness.read('packages/package-manifest.json')
        metadata = json.loads(manifest)
        assert metadata['release_tag'] == TAG
        assert sorted(archive.namelist()) == sorted(['package-manifest.json', *metadata['artifacts']])
        for member, digest in metadata['artifacts'].items():
            assert Path(member).name == member
            raw = archive.read(member)
            assert hashlib.sha256(raw).hexdigest() == digest and raw == witness.read('packages/' + member)
            destination = package / member
            destination.write_bytes(raw)
            if member == 'yuki-feishu':
                destination.chmod(0o700)
        (package / 'package-manifest.json').write_bytes(manifest)
    return {'tag': TAG, 'source_commit': publication['source_commit'], 'asset': name,
            'sha256': asset['sha256'], 'host_source': publication['host_source']}


def published_resources(root, package, output):
    sys.path.insert(0, str(root / 'tests/peers'))
    from feishu_media_wire import cleanup_without_credentials, one

    spec = importlib.util.spec_from_file_location('feishu_resource_fixture', root / 'tests/cases/EXT-005.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    name = 'yuki-feishu.exe' if os.name == 'nt' else 'yuki-feishu'
    binary = package / name
    output.mkdir()
    with TemporaryDirectory(prefix='fs-resource-') as folder:
        Frame, serve = fixture.fixture_imports(root, Path(folder))
        rows = [one(binary, Frame, serve, 'feishu', 'image'), one(binary, Frame, serve, 'lark', 'file')]
        cleanup = cleanup_without_credentials(binary)
    assert rows[0]['sha256'] != rows[1]['sha256']
    for row in rows:
        (output / (row['domain'] + '-wire.json')).write_text(
            json.dumps(row.pop('wire'), indent=2) + '\n', encoding='utf8')
    path = output / 'original-resources.json'
    path.write_text(json.dumps({'status': 'PASS', 'wire_scope': 'scoped Host fixture', 'domains': rows,
                                'erasure_only': cleanup, 'paid_calls': 0}, indent=2) + '\n', encoding='utf8')
    return path


def run(root, output):
    from feishu_owner_check import run as inspect_owners
    from feishu_delivery_check import run as deliver, SCENARIOS, UPLOAD_SCENARIOS, MENTION_SCENARIOS
    published = os.environ.get('YUKI_STABLE_1_1_BUNDLE')
    if published:
        from feishu_release_check import published_host

        host = published_host(root)
    else:
        host = nullcontext((None, None))
    owners = inspect_owners(root, output / 'owners')
    extension = resources = topic = None
    with host as (system, released_host):
        package = None
        if released_host:
            from feishu_topic_check import run as topics

            package = output / 'packages'
            extension = qualified_package(root, system, package)
            assert extension['host_source'] == released_host[1]['source_commit']
            resources = published_resources(root, package, output / 'resources')
            topic = topics(root, output / 'topics', contract='stable-1.1', package_source=package,
                           released_host=released_host)
            assert topic['status'] == 'PASS' and len(topic['cases']) == 3
        delivery = deliver(root, output / 'delivery', package, SCENARIOS, released_host=released_host)
        package = output / 'delivery/packages'
        uploads = deliver(root, output / 'uploads', package, UPLOAD_SCENARIOS, released_host=released_host)
        mentions = deliver(root, output / 'mentions', package, MENTION_SCENARIOS, released_host=released_host)
    assert all(result['status'] == 'PASS' for result in [owners, delivery, uploads, mentions])
    native_cases = len(delivery['cases']) + len(uploads['cases']) + len(mentions['cases'])
    assert native_cases == 84
    return 'lark-rest-receipts.json', {
        'status': 'PASS' if published else 'BLOCKED',
        'card_status': ('FEISHU_REST_AND_OWNER_VERIFIED_ON_PUBLISHED_HOST' if published
                        else 'NATIVE_IMPLEMENTATION_VERIFIED_PUBLIC_CONTRACT_PENDING'),
        'owner_disposition': 'owners/owner-disposition-index.json',
        'owner_status': owners['card_status'],
        'native_receipts': ['delivery/original-delivery.json', 'uploads/original-delivery.json',
                            'mentions/original-delivery.json'],
        'native_cases': native_cases,
        'topic_receipt': 'topics/original-topic.json' if published else None,
        'host_source': released_host[1]['source_commit'] if published else None,
        'extension_published': bool(extension),
        'extension_release': extension,
        'resources_receipt': resources.relative_to(output).as_posix() if resources else None,
        'paid_calls': 0,
        'pending': ['expanded public contract acceptance'] if not published else [],
    }
