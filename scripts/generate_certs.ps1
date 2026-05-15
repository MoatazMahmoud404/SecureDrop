param(
    [string]$CertDir = (Join-Path $PSScriptRoot "..\certs")
)

New-Item -ItemType Directory -Force -Path $CertDir | Out-Null

$certPath = Join-Path $CertDir "cert.pem"
$keyPath = Join-Path $CertDir "key.pem"

function Generate-WithOpenSSL {
    openssl req -x509 -newkey rsa:4096 -keyout $keyPath -out $certPath -days 365 -nodes -subj "/C=EG/ST=Cairo/L=Cairo/O=SecureDrop/CN=localhost"
}

function Generate-WithPythonTrustme {
    $workspaceRoot = Split-Path -Path $PSScriptRoot -Parent
    $pythonPath = Join-Path $workspaceRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $pythonPath)) {
        throw "Python virtual environment not found at $pythonPath"
    }

    & $pythonPath -m pip install trustme | Out-Null
    & $pythonPath -c "from pathlib import Path; import trustme; cert_dir=Path(r'$CertDir'); cert_dir.mkdir(parents=True, exist_ok=True); ca=trustme.CA(); cert=ca.issue_cert('localhost','127.0.0.1'); cert.private_key_pem.write_to_path(cert_dir/'key.pem'); cert.cert_chain_pems[0].write_to_path(cert_dir/'cert.pem')"
}

try {
    Generate-WithOpenSSL
    if (-not ((Test-Path $certPath) -and (Test-Path $keyPath))) {
        throw "OpenSSL did not generate both certificate files."
    }
    Write-Host "Generated TLS certificates with OpenSSL at $CertDir"
}
catch {
    Write-Warning "OpenSSL generation failed. Falling back to Python trustme."
    Generate-WithPythonTrustme
    if (-not ((Test-Path $certPath) -and (Test-Path $keyPath))) {
        throw "Fallback certificate generation failed."
    }
    Write-Host "Generated TLS certificates with Python trustme at $CertDir"
}
