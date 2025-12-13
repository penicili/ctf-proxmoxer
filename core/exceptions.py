class ProxmoxError(Exception):
    """Base exception for Proxmox related errors"""
    pass

class ProxmoxConnectionError(ProxmoxError):
    """Raised when connection to Proxmox fails"""
    pass

class ProxmoxNodeError(ProxmoxError):
    """Raised when there is an issue with the Proxmox node"""
    pass

class ResourceNotFoundError(Exception):
    """Raised when a requested resource is not found"""
    pass

class VMCreationError(ProxmoxError):
    """Raised when VM creation fails"""
    pass
