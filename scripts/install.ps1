$ErrorActionPreference = "Stop"

$DATABASE_URL = "postgresql://jobapplier:jobapplier@localhost:5432/jobapplier"

# Garante que Docker e ferramentas do venv estejam no PATH
$extraPaths = @(
    "C:\Program Files\Docker\Docker\resources\bin",
    "$env:APPDATA\npm"
)
foreach ($p in $extraPaths) {
    if ((Test-Path $p) -and ($env:PATH -notlike "*$p*")) {
        $env:PATH = "$p;$env:PATH"
    }
}

function Write-Step($n, $msg) {
    Write-Host ""
    Write-Host "[$n/7] $msg" -ForegroundColor Cyan
}

function Write-OK($msg) {
    Write-Host "  OK: $msg" -ForegroundColor Green
}

function Write-Fail($msg) {
    Write-Host ""
    Write-Host "  ERRO: $msg" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  AI Job Applier -- Instalacao" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# ------------------------------------------------------------------
# [1/7] Python 3.12+
# ------------------------------------------------------------------
Write-Step 1 "Verificando Python 3.12+"

$pyVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Python nao encontrado. Instale em https://python.org/downloads/ (marque 'Add to PATH')"
}

if ($pyVersion -match "Python (\d+)\.(\d+)") {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 12)) {
        Write-Fail "Python $major.$minor encontrado, mas 3.12+ e necessario. Atualize em https://python.org/downloads/"
    }
    Write-OK "$pyVersion"
} else {
    Write-Fail "Nao foi possivel determinar a versao do Python: $pyVersion"
}

# ------------------------------------------------------------------
# [2/7] Docker Desktop
# ------------------------------------------------------------------
Write-Step 2 "Verificando Docker Desktop"

try {
    $null = docker --version
} catch {
    Write-Fail "Docker nao encontrado. Instale em https://docs.docker.com/desktop/windows/"
}
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Docker nao encontrado. Instale em https://docs.docker.com/desktop/windows/"
}

# Testa se o daemon esta rodando (ignora stderr com Out-Null)
$ErrorActionPreference = "Continue"
docker info 2>&1 | Out-Null
$daemonOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"

if (-not $daemonOk) {
    Write-Host ""
    Write-Host "  ERRO: Docker Desktop esta instalado mas NAO esta rodando." -ForegroundColor Red
    Write-Host "  Abra o Docker Desktop, aguarde o icone ficar estavel na bandeja e rode o script novamente." -ForegroundColor Yellow
    exit 1
}

Write-OK "Docker em execucao"

# ------------------------------------------------------------------
# [3/7] Ambiente virtual
# ------------------------------------------------------------------
Write-Step 3 "Criando ambiente virtual (.venv)"

if (Test-Path ".venv") {
    Write-Host "  .venv ja existe, reutilizando..." -ForegroundColor Yellow
} else {
    python -m venv .venv
    Write-OK ".venv criado"
}

$activateScript = ".\.venv\Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    Write-Fail "Script de ativacao nao encontrado: $activateScript"
}
& $activateScript
Write-OK "Ambiente virtual ativado"

# ------------------------------------------------------------------
# [4/7] Dependencias Python
# ------------------------------------------------------------------
Write-Step 4 "Instalando dependencias (requirements.txt)"

pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Fail "pip install falhou. Veja o erro acima."
}
Write-OK "Dependencias instaladas"

# ------------------------------------------------------------------
# [5/7] Playwright
# ------------------------------------------------------------------
Write-Step 5 "Instalando Playwright (Chromium)"

playwright install chromium --with-deps
if ($LASTEXITCODE -ne 0) {
    Write-Fail "playwright install falhou. Veja o erro acima."
}
Write-OK "Chromium instalado"

# ------------------------------------------------------------------
# [6/7] PostgreSQL via Docker
# ------------------------------------------------------------------
Write-Step 6 "Subindo PostgreSQL via Docker"

docker compose up postgres -d
if ($LASTEXITCODE -ne 0) {
    Write-Fail "docker compose up falhou. Veja o erro acima."
}

Write-Host "  Aguardando PostgreSQL ficar pronto..." -ForegroundColor Yellow

$maxWait  = 60
$elapsed  = 0
$interval = 5
$ready    = $false

while ($elapsed -lt $maxWait) {
    Start-Sleep -Seconds $interval
    $elapsed += $interval

    docker compose exec -T postgres pg_isready -U jobapplier -q 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }

    $attempt = $elapsed / $interval
    $total   = $maxWait / $interval
    Write-Host "  Tentativa $attempt/$total..." -ForegroundColor Yellow
}

if (-not $ready) {
    Write-Fail "PostgreSQL nao ficou disponivel em $maxWait segundos. Logs: docker compose logs postgres"
}

Write-OK "PostgreSQL pronto"

# ------------------------------------------------------------------
# [7/7] Estrutura de dados + Migracoes
# ------------------------------------------------------------------
Write-Step 7 "Criando diretorios e executando migracoes"

$dirs = @(
    "data",
    "data\postgres",
    "data\sessions",
    "data\resumes",
    "data\screenshots",
    "data\reports",
    "data\logs"
)

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}
Write-OK "Diretorios data/ criados"

$env:DATABASE_URL = $DATABASE_URL
alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Fail "alembic upgrade head falhou. Veja o erro acima."
}
Write-OK "Banco de dados inicializado"

# Evita o prompt de e-mail do Streamlit na primeira execucao
$streamlitDir = "$env:USERPROFILE\.streamlit"
$credFile     = "$streamlitDir\credentials.toml"
if (-not (Test-Path $credFile)) {
    New-Item -ItemType Directory -Force $streamlitDir | Out-Null
    Set-Content $credFile "[general]`nemail = `"`""
    Write-OK "Streamlit configurado (sem prompt de e-mail)"
}

# ------------------------------------------------------------------
# Conclusao
# ------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Instalacao concluida com sucesso!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Para iniciar o app, execute:" -ForegroundColor Yellow
Write-Host "  python run.py" -ForegroundColor White
Write-Host ""
Write-Host "O browser abrira em: http://localhost:8501" -ForegroundColor Yellow
Write-Host ""
