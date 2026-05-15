from socket_server.server import _parse_download_command, _parse_upload_command


def test_parse_upload_command_supports_spaces_in_filename() -> None:
    token, file_name, file_size = _parse_upload_command(
        "UPLOAD tok_123 my interview notes.txt 2048"
    )
    assert token == "tok_123"
    assert file_name == "my interview notes.txt"
    assert file_size == 2048


def test_parse_download_command_supports_spaces_in_filename() -> None:
    token, file_name = _parse_download_command(
        "DOWNLOAD tok_123 final report 2026.pdf")
    assert token == "tok_123"
    assert file_name == "final report 2026.pdf"
