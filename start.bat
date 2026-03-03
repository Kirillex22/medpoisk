@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo     Запуск FastAPI приложения
echo ========================================
echo.

REM 1) Проверка наличия Python 3.10+
echo [1/4] Проверка версии Python...

python --version 2>nul | findstr /R "3\.1[0-9]\. 3\.[2-9][0-9]\." >nul
if errorlevel 1 (
    echo [ОШИБКА] Python 3.10 или выше не найден!
    echo Установите Python 3.10+ и добавьте его в PATH
    pause
    exit /b 1
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set python_version=%%i
    echo [OK] Найден Python !python_version!
)

echo.

REM 2) Проверка и создание виртуального окружения
echo [2/4] Проверка виртуального окружения...

if not exist ".venv" (
    echo Виртуальное окружение не найдено. Создаю...
    python -m venv .venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать виртуальное окружение
        pause
        exit /b 1
    )
    echo [OK] Виртуальное окружение создано
) else (
    echo [OK] Виртуальное окружение существует
)

echo.

REM Активация виртуального окружения
echo Активация виртуального окружения...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ОШИБКА] Не удалось активировать виртуальное окружение
    pause
    exit /b 1
)
echo [OK] Виртуальное окружение активировано
echo.

REM 3) Проверка и установка зависимостей
echo [3/4] Проверка зависимостей...

if exist "requirements.txt" (
    echo Проверка установленных пакетов...
    
    REM Проверяем, установлены ли основные пакеты
    pip list --format=freeze > installed.tmp
    set packages_installed=0
    
    for /f %%i in (requirements.txt) do (
        findstr /i "%%i" installed.tmp >nul || set packages_installed=1
    )
    
    del installed.tmp 2>nul
    
    if !packages_installed! equ 1 (
        echo Устанавливаю зависимости из requirements.txt...
        pip install -r requirements.txt
        if errorlevel 1 (
            echo [ОШИБКА] Не удалось установить зависимости
            pause
            exit /b 1
        )
        echo [OK] Зависимости установлены
    ) else (
        echo [OK] Все зависимости уже установлены
    )
) else (
    echo [ВНИМАНИЕ] Файл requirements.txt не найден
)

echo.

REM 4) Запуск uvicorn
echo [4/4] Запуск FastAPI приложения...
echo.

REM Проверяем существование файла main.py
if not exist "main.py" (
    echo [ВНИМАНИЕ] Файл main.py не найден в текущей директории
    echo Текущая директория: %cd%
    echo.
    echo Пытаюсь найти main.py в поддиректориях...
    
    dir /s /b main.py 2>nul | findstr "main.py" >nul
    if errorlevel 1 (
        echo [ОШИБКА] Файл main.py не найден
        pause
        exit /b 1
    ) else (
        echo [OK] Файл main.py найден где-то в поддиректориях
    )
)

echo Запуск сервера...
echo Для остановки нажмите Ctrl+C
echo.
echo Страница чата доступна по адресу: http://localhost:8000
echo Документация API: http://localhost:8000/docs
echo.

uvicorn src.main:app --reload

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось запустить uvicorn
    echo Возможно, uvicorn не установлен или произошла другая ошибка
    pause
    exit /b 1
)

pause