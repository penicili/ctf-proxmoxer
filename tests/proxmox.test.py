"""
Test script untuk Proxmox Service
Simple test untuk melihat VM yang ada
"""
from services import ProxmoxService
from core.logging import logger
from config.settings import settings


def test_proxmox():
    """Test koneksi ke Proxmox dan list VMs"""
    
    logger.info("=" * 60)
    logger.info("Testing Proxmox - List VMs")
    logger.info("=" * 60)
    
    # Display config
    logger.info(f"\n📋 Configuration:")
    logger.info(f"  Host: {settings.PROXMOX_HOST}")
    logger.info(f"  User: {settings.PROXMOX_USER}")
    logger.info(f"  Node: {settings.PROXMOX_NODE}")
    
    # Create service instance
    proxmox = ProxmoxService()
    
    # Test connection
    logger.info(f"\n🔌 Connecting to Proxmox...")
    if not proxmox.connect():
        logger.error("❌ Connection failed!")
        logger.info("\n💡 Tips:")
        logger.info("  1. Pastikan Proxmox server running")
        logger.info("  2. Copy .env.example ke .env")
        logger.info("  3. Isi kredensial Proxmox di .env")
        return False
    
    # List VMs
    logger.info(f"\n📋 Listing VMs/Containers...")
    vms = proxmox.list_vms()
    
    # Test create vm with dummy config data
    logger.info(f"Creating test VM with dummy config data...")
    testvm = proxmox.create_vm(
        team="test-team",
        level_id=1,
        time_limit=30,
        config={ "memory": 256, "cores": 1 }
    )
    if testvm:
        logger.success(f"✅ Test VM created: VMID {testvm}")
    
    # logger.info(f"stopping test vm")
    # if proxmox.stop_vm(testvm):
    #     logger.success(f"✅ Test VM stopped: VMID {testvm}")
    # else:
    #     logger.error(f"❌ Failed to stop Test VM: VMID {testvm}")
    
    
    if vms:
        logger.info(f"\n✅ Found {len(vms)} VMs/Containers:\n")
        
        # Group by status
        running = [vm for vm in vms if vm['status'] == 'running']
        stopped = [vm for vm in vms if vm['status'] == 'stopped']
        
        if running:
            logger.info(f"🟢 Running ({len(running)}):")
            for vm in running:
                logger.info(f"   VMID {vm['vmid']:>3}: {vm['name']:<30} [{vm['type']}]")
        
        if stopped:
            logger.info(f"\n🔴 Stopped ({len(stopped)}):")
            for vm in stopped:
                logger.info(f"   VMID {vm['vmid']:>3}: {vm['name']:<30} [{vm['type']}]")
    else:
        logger.info("  No VMs found")
    
    logger.info("\n" + "=" * 60)
    logger.success("✅ Test completed!")
    logger.info("=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        test_proxmox()
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        logger.error(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
