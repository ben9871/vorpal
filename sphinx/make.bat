@ECHO OFF
pushd %~dp0

if "%1" == "" goto help

set SPHINXBUILD=sphinx-build
set SOURCEDIR=.
set BUILDDIR=_build

%SPHINXBUILD% -M %1 %SOURCEDIR% %BUILDDIR% %SPHINXOPTS% %O%
goto end

:help
%SPHINXBUILD% -M help %SOURCEDIR% %BUILDDIR% %SPHINXOPTS% %O%

:end
popd
