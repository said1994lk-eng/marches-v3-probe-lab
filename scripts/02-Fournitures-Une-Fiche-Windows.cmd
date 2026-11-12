@echo off
setlocal
cd /d "%~dp0.."
echo.
echo ================================================
echo  Marches Intelligence V3 - Gate 1B-02 local
echo ================================================
echo Ce test peut effectuer UN POST de recherche Fournitures
echo et ouvrir UNE page de detail publique maximum.
echo PAS de login, DCE, download, base de donnees, pagination ou retry.
echo A executer UNIQUEMENT si le test de connexion a reussi.
echo.
if not exist ".venv\Scripts\python.exe" (
  echo Executez d'abord 01-Test-Connexion-Windows.cmd
  pause
  exit /b 1
)
choice /C ON /N /M "Confirmer ce test public unique? [O] Oui / [N] Non: "
if errorlevel 2 exit /b 0
if errorlevel 1 (
  ".venv\Scripts\python.exe" scripts\local_connection_check.py --mode category --ack-one-post-one-detail
  set "code=%errorlevel%"
  echo.
  echo Rapport local dans local-reports.
  echo Un seul detail Fournitures ne prouve PAS toutes les annonces.
  pause
  exit /b %code%
)
exit /b 1
