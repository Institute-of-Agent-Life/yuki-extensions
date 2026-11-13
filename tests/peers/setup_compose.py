"""Launch only the pinned CORE-039 service in an isolated Compose project."""

import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
from pathlib import Path
import tempfile
from uuid import uuid4

from package import build


def command(args, *, cwd=None, env=None, timeout=30):
    return subprocess.run(args, cwd=cwd, env=env, check=True, capture_output=True, text=True, timeout=timeout).stdout


def inspect(kind, name, template):
    return json.loads(command(["docker", kind, "inspect", name, "--format", "{{json " + template + "}}"]))


@contextmanager
def ingress_network(name):
    command(["docker", "network", "create", "--internal", "--label", "yuki.acceptance=EXT-040", name])
    try:
        assert inspect("network", name, ".Internal") is True
        yield
    finally:
        command(["docker", "network", "rm", name])


def compose(kit, env, *args, timeout=30):
    return command(["docker", "compose", *args], cwd=kit, env=env, timeout=timeout)


def operator(run, *args):
    return json.loads(run("exec", "-T", "core", "yuki-core", "--data", "/var/tmp/yuki", "operator", *args))


def launch(run, name, image, network=None):
    run("up", "--detach", "--pull", "never", "--no-build", "--wait", "--wait-timeout", "30", timeout=45)
    container = run("ps", "-q", "core").strip()
    assert inspect("container", container, ".Config.Image") == image
    assert inspect("container", container, ".State.Health.Status") == "healthy"
    assert not inspect("container", container, ".HostConfig.PortBindings")
    host = inspect("container", container, ".HostConfig")
    assert host["ReadonlyRootfs"] is True and host["CapDrop"] == ["ALL"]
    assert host["Privileged"] is False and host["NetworkMode"] == (network or "none")
    settings = dict(line.split("=", 1) for line in inspect("container", container, ".Config.Env"))
    assert set(settings) == {"TZ", "PATH"} and settings["TZ"] == "Asia/Shanghai"
    mounts = inspect("container", container, ".Mounts")
    assert [(m["Type"], m["Name"], m["Destination"]) for m in mounts] == [
        ("volume", name + "_owner", "/var/tmp")
    ]
    assert run("ps", "--services", "--status", "running").split() == ["core"]
    db = operator(run, "database-info")
    assert db["foreign_keys"] == 1 and db["journal_mode"] == "wal"
    return {"health": "healthy", "project": name, "network_mode": host["NetworkMode"],
            "volume": mounts[0]["Name"], "mount": mounts[0]["Destination"], "schema_version": db["schema_version"]}


def check_peer(image, network, name):
    alias = name + "-core"
    peer = [
        "docker", "run", "--rm", "--pull", "never", "--network", network,
        "--entrypoint", "/bin/bash", image, "-ec",
        'exec 3<>"/dev/tcp/$1/8080"; printf "GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n" "$2" "$1" >&3; cat <&3',
        "http-check", alias,
    ]
    response = command([*peer, "/readyz"], timeout=12)
    headers, body = response.split("\n\n", 1)
    assert headers.splitlines()[0] == "HTTP/1.1 200 OK"
    assert json.loads(body) == {"ready": True}
    assert command([*peer, "/onebot/42"], timeout=12).startswith("HTTP/1.1 404 ")


def launch_pair(local, external, env, image, network):
    direct = partial(compose, local, env)
    ingress = partial(compose, external, env)
    names = [json.loads(run("config", "--format", "json"))["name"] for run in (direct, ingress)]
    assert local.name == external.name
    assert len(set(names)) == 2, f"same basename kits share a Compose project: {names}"
    assert all(re.fullmatch(r"yuki-[0-9a-f]{32}", name) for name in names)
    with ingress_network(network):
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                local_start = pool.submit(launch, direct, names[0], image)
                external_start = pool.submit(launch, ingress, names[1], image, network)
                local_state = local_start.result()
                external_state = external_start.result()
            assert local_state["volume"] != external_state["volume"]
            check_peer(image, network, names[1])
            external_state.update(peer_ready=True, unconfigured_qq_http_status=404)

            direct_marker = operator(direct, "set-label", "local-owner")
            external_marker = operator(ingress, "set-label", "external-owner")
            assert operator(direct, "get-label") == direct_marker == {"value": "local-owner", "revision": 1}
            assert operator(ingress, "get-label") == external_marker == {"value": "external-owner", "revision": 1}
            direct("down", "--timeout", "5")
            assert not direct("ps", "-q", "core").strip()
            assert operator(ingress, "get-label") == external_marker
            check_peer(image, network, names[1])
            launch(direct, names[0], image)
            assert operator(direct, "get-label") == direct_marker
            local_state["owner_survived_recreate"] = True
            external_state["survived_other_project_down"] = True
            return local_state, external_state
        finally:
            with ThreadPoolExecutor(max_workers=2) as pool:
                cleanups = [pool.submit(run, "down", "--volumes", "--timeout", "5") for run in (direct, ingress)]
                for cleanup in cleanups:
                    cleanup.result()


def verify(root, output):
    archive = Path(os.environ["YUKI_CORE039_OCI"]).resolve(strict=True)
    pin = json.loads((root / "tools/yuki-setup/inputs/source.lock.json").read_bytes())
    release = build(root, "yuki-setup", output / "packages")
    exe = output / "packages" / ("yuki-setup.exe" if os.name == "nt" else "yuki-setup")
    env = {key: val for key, val in os.environ.items()
           if not key.startswith("COMPOSE_") and key != "YUKI_TIMEZONE"}
    actions = []
    secret = "fixture-secret-reference-preserve"

    def setup(action, kit, *options, source=archive, refusal=None):
        result = subprocess.run([exe, action, "--archive", source, "--dir", kit, *options],
                                env=env, capture_output=True, text=True, timeout=90)
        assert secret not in result.stdout + result.stderr
        if refusal is None:
            assert result.returncode == 0, result.stderr
        else:
            assert result.returncode != 0 and refusal in result.stderr, result.stderr
        actions.append({"command": action, "directory": kit.name, "options": options, "refused": refusal})
        return result.stdout

    with tempfile.TemporaryDirectory(prefix="ext040-compose-") as temp:
        work = Path(temp)
        local = work / "direct" / "kit"
        setup("init", local, "--core", pin["core_version"], "--profile", "direct")
        local_yaml = (local / "compose.yaml").read_bytes()
        without_name = re.sub(rb"^name: yuki-[0-9a-f]{32}\n", b"", local_yaml, flags=re.MULTILINE)
        assert without_name == (root / "deploy/compose/direct.yaml").read_bytes()
        assert without_name != local_yaml
        setup("init", local, "--timezone", "Asia/Shanghai")
        assert (local / ".env").read_bytes() == b"YUKI_TIMEZONE=Asia/Shanghai\n"
        assert (local / "compose.yaml").read_bytes() == local_yaml
        setup("doctor", local)

        legacy = work / "legacy-env"
        legacy.mkdir()
        env_file = legacy / ".env"
        original_env = (f"# operator comment\r\nNAPCAT_HOME=old-value\r\n"
                        f"OPENAI_KEY_REF={secret}\r\nYUKI_TIMEZONE=   # keep this comment\r\n").encode()
        env_file.write_bytes(original_env)
        soul = legacy / "SOUL.example.md"
        soul.write_bytes(b"# hand-maintained SOUL example\r\n")
        setup("init", legacy, "--timezone", "Asia/Shanghai")
        compose_file = legacy / "compose.yaml"
        comment = b"# retained compose comment\n"
        compose_file.write_bytes(comment + compose_file.read_bytes())
        preserved = compose_file.read_bytes()
        setup("init", legacy, "--timezone", "UTC")
        assert env_file.read_bytes() == original_env.replace(b"   #", b"   UTC #")
        assert compose_file.read_bytes() == preserved
        assert soul.read_bytes() == b"# hand-maintained SOUL example\r\n"
        setup("doctor", legacy, "--timezone", "UTC")

        previous = work / "previous-kit"
        previous.mkdir()
        previous_compose = (root / "tests/fixtures/EXT-040/legacy-direct.yaml").read_bytes()
        (previous / "compose.yaml").write_bytes(previous_compose)
        assert "storage=legacy-bind" in setup("init", previous, "--timezone", "Asia/Shanghai")
        assert (previous / "compose.yaml").read_bytes() == previous_compose
        assert "storage=legacy-bind" in setup("doctor", previous)

        named_volume_kit = work / "previous-named-volume-kit"
        named_volume_kit.mkdir()
        (named_volume_kit / "compose.yaml").write_bytes(without_name)
        assert "project=compose-default" in setup("init", named_volume_kit, "--timezone", "Asia/Shanghai")
        assert (named_volume_kit / "compose.yaml").read_bytes() == without_name
        assert "project=compose-default" in setup("doctor", named_volume_kit)
        old_volume = json.loads(compose(named_volume_kit, env, "config", "--format", "json"))["volumes"]["owner"]
        assert old_volume["name"] == "previous-named-volume-kit_owner"

        for name, options, reason in [
            ("missing-monty", ("--profile", "code"), "no compatible pinned package"),
            ("missing-snowluma", ("--plugin", "snowluma"), "no compatible pinned package"),
            ("missing-network", ("--entry", "external"), "requires a valid --entry-network"),
            ("bad-network", ("--entry", "external", "--entry-network", "bad\nnet"), "requires a valid --entry-network"),
            ("network-with-local", ("--entry-network", "gateway"), "use --entry local or"),
            ("wrong-core", ("--core", "other"), "does not match the verified input"),
        ]:
            dest = work / name
            setup("init", dest, *options, refusal=reason)
            assert not dest.exists()

        foreign = work / "foreign"
        foreign.mkdir()
        foreign_file = foreign / "compose.yaml"
        foreign_file.write_bytes(b"services: {foreign: {image: operator}}\n")
        setup("init", foreign, refusal="differs from the pinned offline kit")
        assert foreign_file.read_bytes() == b"services: {foreign: {image: operator}}\n"
        assert not (foreign / ".env").exists()
        corrupt = work / "bad.oci"
        corrupt.write_bytes(b"wrong candidate")
        setup("doctor", local, source=corrupt, refusal="offline input refused")

        external = work / "external" / "kit"
        name = "ext040-" + uuid4().hex[:12]
        network = name + "-ingress"
        options = ("--entry", "external", "--entry-network", network)
        setup("init", external, *options, "--timezone", "Asia/Shanghai")
        external_yaml = (external / "compose.yaml").read_bytes()
        setup("init", external, *options, "--timezone", "Asia/Shanghai")
        setup("doctor", external, *options)
        setup("init", external, "--entry", "external", "--entry-network", network + "-wrong",
              refusal="differs from the pinned offline kit")
        assert (external / "compose.yaml").read_bytes() == external_yaml

        image = "yuki-core@" + pin["image_digest"]
        assert image in inspect("image", image, ".RepoDigests")
        local_state, external_state = launch_pair(local, external, env, image, network)

    return {
        "status": "PASS",
        "candidate_source": pin["source_commit"],
        "image": image,
        "oci_sha256": pin["archive_sha256"],
        "docker_server": command(["docker", "version", "--format", "{{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}"]).strip(),
        "compose_version": command(["docker", "compose", "version", "--short"]).strip(),
        "installer": release["artifacts"],
        "actions": actions,
        "direct_without_monty": local_state,
        "no_qq_external_entry": external_state,
        "legacy_napcat_env_preserved": True,
        "previous_named_volume_preserved": old_volume["name"],
        "registry_pulls": 0,
        "paid_calls": 0,
    }
