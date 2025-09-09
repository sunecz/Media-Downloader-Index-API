LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': True,
        },
        'granian': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
        'granian.access': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': True,
        },
        'granian.error': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': True,
        },
        'httpx': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': True,
        },
    },
}
