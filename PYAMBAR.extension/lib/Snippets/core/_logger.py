# -*- coding: utf-8 -*-
"""
Logging Module - PYAMBAR(lab)

Sistema centralizado de logging com loguru para todas as ferramentas.

Uso:
    from lib.Snippets.core._logger import get_logger

    logger = get_logger("ColorSplasher")
    logger.info("Iniciando processamento")
    logger.success("Operação concluída!")
    logger.warning("Atenção: parâmetro vazio")
    logger.error("Erro ao processar: {}", error_msg)

Author: Thiago Barreto Sobral Nunes
Version: 1.0.0
"""
import os
import sys
from datetime import datetime

try:
    from loguru import logger as _logger
    LOGURU_AVAILABLE = True
except ImportError:
    LOGURU_AVAILABLE = False
    _logger = None


def get_logger(tool_name, enable_console=False, enable_file=True):
    """
    Obtém logger configurado para uma ferramenta específica.

    Args:
        tool_name (str): Nome da ferramenta (ex: "ColorSplasher")
        enable_console (bool): Habilitar saída no console (default: False)
        enable_file (bool): Habilitar gravação em arquivo (default: True)

    Returns:
        logger: Instância do logger configurada

    Example:
        >>> logger = get_logger("ColorSplasher")
        >>> logger.info("Processando {} elementos", 150)
    """
    if not LOGURU_AVAILABLE:
        # Fallback: retorna objeto mock se loguru não disponível
        return _create_fallback_logger(tool_name)

    # Remover handlers padrão
    _logger.remove()

    # Configurar console se solicitado
    if enable_console:
        _logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{extra[tool]}</cyan> - <level>{message}</level>",
            level="DEBUG",
            colorize=True,
        )

    # Configurar arquivo de log
    if enable_file:
        # Determinar diretório de logs
        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        log_dir = os.path.join(script_dir, "logs")

        # Criar diretório se não existe
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except Exception:
                pass  # Se falhar, não loga em arquivo

        # Arquivo de log da ferramenta
        log_file = os.path.join(log_dir, "{tool}_{date}.log")

        if os.path.exists(log_dir):
            _logger.add(
                log_file,
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[tool]} | {message}",
                level="DEBUG",
                rotation="1 week",
                retention="1 month",
                compression="zip",
                encoding="utf-8",
                enqueue=True,  # Thread-safe
            )

    # Adicionar contexto da ferramenta
    return _logger.bind(tool=tool_name)


def _create_fallback_logger(tool_name):
    """
    Cria logger básico quando loguru não está disponível.
    """
    class FallbackLogger:
        def __init__(self, name):
            self.name = name

        def _log(self, level, message, *args):
            timestamp = datetime.now().strftime("%H:%M:%S")
            msg = message.format(*args) if args else message
            print("[{}] {} - {}: {}".format(timestamp, level, self.name, msg))

        def debug(self, message, *args):
            self._log("DEBUG", message, *args)

        def info(self, message, *args):
            self._log("INFO", message, *args)

        def success(self, message, *args):
            self._log("SUCCESS", message, *args)

        def warning(self, message, *args):
            self._log("WARNING", message, *args)

        def error(self, message, *args):
            self._log("ERROR", message, *args)

        def critical(self, message, *args):
            self._log("CRITICAL", message, *args)

        def exception(self, message, *args):
            self._log("EXCEPTION", message, *args)

    return FallbackLogger(tool_name)


# Funções de conveniência
def log_transaction_start(logger, description):
    """Log do início de uma transação."""
    logger.info("🔄 Iniciando transação: {}", description)


def log_transaction_success(logger, description, count=None):
    """Log de transação bem-sucedida."""
    if count:
        logger.success("✓ Transação concluída: {} ({} elementos)", description, count)
    else:
        logger.success("✓ Transação concluída: {}", description)


def log_transaction_error(logger, description, error):
    """Log de erro em transação."""
    logger.error("✗ Erro na transação '{}': {}", description, str(error))


def log_element_processing(logger, element_name, count, total):
    """Log de progresso de processamento de elementos."""
    progress = (count / total * 100) if total > 0 else 0
    logger.debug("Processando: {} ({}/{} - {:.1f}%)", element_name, count, total, progress)
