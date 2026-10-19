@echo off
REM Serve the StackDesigner LIF Export Adjuster web page locally and open it.
REM The page must be served over HTTP (Brython cannot fetch local files via file://).

set "PORT=8777"

start "" "http://localhost:%PORT%/"

py -m http.server %PORT% --directory "%~dp0docs"
