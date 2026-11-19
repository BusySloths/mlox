from mlox.infra import Bundle
from mlox.project import ProjectWorkspace
from mlox.servers.ubuntu.native import UbuntuNativeServer


def test_firewall_draft_persists_without_touching_the_server(tmp_path):
    path = str(tmp_path / "draft")
    workspace = ProjectWorkspace.create(path, "pw")
    server = UbuntuNativeServer(ip="192.0.2.1", root="root", root_pw="", service_config_id="test", port="2222")
    workspace.infrastructure.bundles.append(Bundle(name="server", server=server))
    workspace.commit()

    result = workspace.add_firewall_draft_source(ip="server", source="192.0.2.8/24")
    assert result.success
    assert result.data["applied"] is False
    assert result.data["trusted_sources"] == ["192.0.2.0/24"]

    reopened = ProjectWorkspace.open(path, "pw")
    preview = reopened.preview_server_firewall(ip="server")
    assert preview.data["draft_saved"] is True
    assert preview.data["public_tcp_ports"] == [80, 443, 2222]
    assert preview.data["trusted_sources"] == ["192.0.2.0/24"]
    assert not reopened.add_firewall_draft_source(ip="server", source="0.0.0.0/0").success
    assert reopened.preview_server_firewall(ip="server").data["trusted_sources"] == ["192.0.2.0/24"]
    assert reopened.remove_firewall_draft_source(ip="server", source="192.0.2.0/24").success
    assert ProjectWorkspace.open(path, "pw").preview_server_firewall(ip="server").data["trusted_sources"] == []


def test_replace_sources_is_atomic_and_preserves_public_ports(tmp_path):
    path = str(tmp_path / "replace")
    workspace = ProjectWorkspace.create(path, "pw")
    server = UbuntuNativeServer(ip="192.0.2.1", root="root", root_pw="", service_config_id="test", port="2222")
    workspace.infrastructure.bundles.append(Bundle(name="server", server=server))
    workspace.commit()
    assert workspace.replace_firewall_draft_sources(ip="server", sources=["192.0.2.2", "2001:db8::1"]).success
    result = workspace.replace_firewall_draft_sources(ip="server", sources=["192.0.2.3", "0.0.0.0/0"])
    assert not result.success
    preview = ProjectWorkspace.open(path, "pw").preview_server_firewall(ip="server")
    assert preview.data["public_tcp_ports"] == [80, 443, 2222]
    assert preview.data["trusted_sources"] == ["192.0.2.2", "2001:db8::1"]
