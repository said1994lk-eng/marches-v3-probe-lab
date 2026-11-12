@echo off
setlocal
cd /d "%~dp0.."
echo.
echo ================================================
echo  Marches Intelligence V3 - Connexion publique
echo ================================================
echo Ce test ne fait aucun login, depot, DCE ou pagination.
echo Au maximum deux routes publiques, sans retry automatique.
echo.
if not exist ".venv\Scripts\python.exe" (
  echo Creation de l'environnement Python...
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    where python >nul 2>&1
    if errorlevel 1 (
      echo ERREUR: Installez Python 3.12 avec l'option Add Python to PATH.
      pause
      exit /b 1
    )
    python -m venv .venv
  )
  if errorlevel 1 (
    echo ERREUR: Creation de .venv impossible.
    pause
    exit /b 1
  )
)
echo Verification des dependances...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo ERREUR: installation de playwright.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
  echo ERREUR: installation de Chromium.
  pause
  exit /b 1
)
echo.
echo Test unique depuis CE PC: connexion a la recherche publique...
".venv\Scripts\python.exe" scripts\local_connection_check.py --mode connection
set "code=%errorlevel%"
echo.
echo Le rapport JSON se trouve dans le dossier local-reports
echo Si le statut est FORM_READY_CONFIRMED_ONCE, connexion OK pour CE test.
echo Sinon, ne repetez pas les tentatives: partagez uniquement le JSON.
echo.
pause
exit /b %code%
