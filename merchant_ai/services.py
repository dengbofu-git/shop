"""Version 0.1 describes the entry only; no model or business tools are loaded."""

from . import __version__


def assistant_status():
    return {
        'module': 'merchant_ai',
        'version': __version__,
        'status': 'initialized',
        'title': '商家智能助手',
        'message': '商家智能助手入口已开放，具体功能正在准备中。',
        'chat_enabled': False,
        'model_connected': False,
        'capabilities': [],
    }
