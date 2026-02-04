# Assinatura de Codigo - PYAMBAR

Este documento explica como configurar assinatura digital de codigo para o instalador PYAMBAR, eliminando bloqueios do Windows SmartScreen.

## Por que Assinar?

Executaveis nao assinados sao bloqueados pelo Windows porque:
- SmartScreen nao pode verificar a origem
- Antiviruses flagam binarios "desconhecidos"
- Usuarios recebem avisos assustadores

Com assinatura digital:
- Windows reconhece o publicador
- SmartScreen permite execucao sem avisos
- Usuarios confiam no instalador

---

## Opcao 1: SignPath.io (Gratuito para Open-Source)

SignPath oferece assinatura de codigo gratuita para projetos open-source.

### Passo 1: Criar Conta

1. Acesse [signpath.io](https://signpath.io)
2. Clique em **"Open Source"**
3. Faca login com sua conta GitHub
4. Submeta seu projeto para aprovacao (prove que e open-source)

### Passo 2: Configurar Projeto

Apos aprovacao, configure o projeto no painel SignPath:

1. **Project Name**: PYAMBAR
2. **Repository**: github.com/thiagobarretosn-hue/PYAMBAR
3. **Artifact Configuration**: Selecione os arquivos a serem assinados

### Passo 3: Criar Signing Policy

```yaml
# signpath.yaml
artifact_configurations:
  - name: installer
    paths:
      - "installer/dist/*.exe"
    signing_policies:
      - name: release-signing
        certificate: open-source-certificate
```

### Passo 4: Integrar com GitHub Actions

SignPath se integra automaticamente com GitHub Actions. Veja a secao de GitHub Actions abaixo.

---

## Opcao 2: Certificado Proprio (Pago)

Para maior controle, adquira um certificado de assinatura de codigo:

### Provedores Recomendados

| Provedor | Preco/ano | Observacao |
|----------|-----------|------------|
| **Sectigo** | ~$70 | Mais barato, aceito globalmente |
| **DigiCert** | ~$500 | Premium, suporte excelente |
| **SSL.com** | ~$100 | Bom custo-beneficio |
| **Certum** | ~$60 | Europeu, barato |

### Processo de Compra

1. Escolha um provedor acima
2. Compre certificado "Code Signing" (nao SSL)
3. Complete verificacao de identidade (leva 1-3 dias)
4. Receba certificado (.pfx ou token USB)

### Assinatura Local

Com o certificado instalado:

```powershell
# Assinar com signtool (Windows SDK)
signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a "installer\dist\PYAMBAR_Installer.exe"

# Verificar assinatura
signtool verify /pa "installer\dist\PYAMBAR_Installer.exe"
```

---

## Opcao 3: Certificado Auto-Assinado (Desenvolvimento)

Para testes, crie um certificado auto-assinado:

```powershell
# Criar certificado (PowerShell como Admin)
$cert = New-SelfSignedCertificate `
    -Subject "CN=PYAMBAR Dev, O=Thiago Barreto" `
    -Type CodeSigningCert `
    -CertStoreLocation Cert:\CurrentUser\My

# Exportar para .pfx
$password = ConvertTo-SecureString -String "SenhaSegura123" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath ".\pyambar_dev.pfx" -Password $password

# Assinar
Set-AuthenticodeSignature -FilePath "installer\dist\PYAMBAR_Installer.exe" -Certificate $cert -TimestampServer "http://timestamp.digicert.com"
```

> **Nota:** Certificados auto-assinados NAO eliminam avisos do SmartScreen. Sao uteis apenas para desenvolvimento/testes.

---

## GitHub Actions - Build Automatizado

### Arquivo: .github/workflows/build-installer.yml

```yaml
name: Build Installer

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:

jobs:
  build:
    runs-on: windows-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r installer/requirements.txt

      - name: Build executable
        run: |
          cd installer
          pyinstaller --onefile --windowed --name "PYAMBAR_Installer" --clean pyambar_installer.py

      - name: Sign with SignPath (se configurado)
        if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/')
        uses: signpath/github-action-submit-signing-request@v1
        with:
          api-token: ${{ secrets.SIGNPATH_API_TOKEN }}
          organization-id: ${{ secrets.SIGNPATH_ORG_ID }}
          project-slug: pyambar
          signing-policy-slug: release-signing
          artifact-configuration-slug: installer
          github-artifact-id: installer-unsigned

      - name: Generate SHA256 hash
        run: |
          Get-FileHash installer\dist\PYAMBAR_Installer.exe -Algorithm SHA256 | Format-List

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: PYAMBAR_Installer
          path: installer/dist/PYAMBAR_Installer.exe

      - name: Create Release
        if: startsWith(github.ref, 'refs/tags/')
        uses: softprops/action-gh-release@v2
        with:
          files: |
            installer/dist/PYAMBAR_Installer.exe
            installer/Install-PYAMBAR.ps1
          body: |
            ## PYAMBAR ${{ github.ref_name }}

            ### Download
            - **Instalador**: `PYAMBAR_Installer.exe`
            - **Script PowerShell**: `Install-PYAMBAR.ps1`

            ### Verificacao de Integridade
            ```
            SHA256 (PYAMBAR_Installer.exe): [hash sera adicionado]
            ```

            ### Instalacao
            Veja instrucoes completas no [README](https://github.com/thiagobarretosn-hue/PYAMBAR#instalacao)
```

---

## Verificacao de Assinatura

### Para Usuarios

Verificar se o executavel esta assinado:

1. Clique com botao direito no .exe
2. **Propriedades** → aba **Assinaturas Digitais**
3. Verifique se ha assinatura valida

### Via PowerShell

```powershell
# Verificar assinatura
Get-AuthenticodeSignature "PYAMBAR_Installer.exe"

# Saida esperada (assinado):
# SignerCertificate: [Thumbprint: ABC123...]
# Status: Valid
```

---

## Proximos Passos

1. **Imediato**: Usar script PowerShell (Install-PYAMBAR.ps1) como alternativa
2. **Curto prazo**: Aplicar para SignPath.io (gratuito)
3. **Longo prazo**: Considerar certificado proprio se necessario

---

## Referencias

- [SignPath Documentation](https://about.signpath.io/documentation)
- [Microsoft Code Signing](https://docs.microsoft.com/en-us/windows/win32/seccrypto/cryptography-tools)
- [PyInstaller + Code Signing](https://pyinstaller.org/en/stable/feature-notes.html#windows-code-signing)
