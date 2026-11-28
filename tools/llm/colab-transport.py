import re

def classify(raw):
    categories={
        "CONNECTION_LOST":r"Connection was lost|WebSocketConnectionClosedException|Connection reset",
        "KERNEL_GONE":r"Kernel (?:dead|restarting)",
        "SESSION_GONE":r"Session .* not found|session .* appears to be lost",
        "AUTH":r"\b401\b|\b403\b|invalid_grant|unauthorized",
        "TIMEOUT":r"timed out|TimeoutError|Timeout waiting",
        "FILE_UNAVAILABLE":r"FileNotFoundError|File or directory not found|\b404\b",
    }
    return next((k for k,p in categories.items() if re.search(p,raw,re.I)),"UNCLASSIFIED")

