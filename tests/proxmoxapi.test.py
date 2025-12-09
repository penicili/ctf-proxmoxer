"""
Testing buat ngeliat Response Proxmox API
"""
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from proxmoxer import ProxmoxAPI
from config.settings import settings
import json
import time
from datetime import datetime

def test_vm_operations():
    """Test VM operations dan lihat response API"""
    
    # Prepare result storage
    results = {
        "timestamp": datetime.now().isoformat(),
        "node": settings.PROXMOX_NODE,
        "host": settings.PROXMOX_HOST,
        "endpoints": {},
        "responses": {}
    }
    
    # 1. Connect ke Proxmox
    print("=" * 60)
    print("CONNECTING TO PROXMOX")
    print("=" * 60)
    
    try:
        proxmox = ProxmoxAPI(
            settings.PROXMOX_HOST,
            user=settings.PROXMOX_USER,
            password=settings.PROXMOX_PASSWORD,
            verify_ssl=settings.PROXMOX_VERIFY_SSL
        )
        print("✅ Connected successfully\n")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return
    
    node = settings.PROXMOX_NODE
    
    # Ganti dengan VMID yang ada di Proxmox Anda
    vmid = input("Enter VMID to test (e.g., 100): ").strip()
    if not vmid:
        print("❌ VMID required")
        return
    
    vmid = int(vmid)
    results["vmid"] = vmid
    
    # 2. Get VM Status (Current)
    endpoint_status = f"/nodes/{node}/qemu/{vmid}/status/current"
    print("\n" + "=" * 60)
    print("GET VM STATUS (CURRENT)")
    print(f"Endpoint: GET {endpoint_status}")
    print("=" * 60)
    
    try:
        status = proxmox.nodes(node).qemu(vmid).status.current.get()
        results["endpoints"]["status_initial"] = {"method": "GET", "path": endpoint_status}
        results["responses"]["status_initial"] = status
        print(json.dumps(status, indent=2))
        current_status = status.get('status', 'unknown')
        print(f"\n📊 Current Status: {current_status}")
    except Exception as e:
        print(f"❌ Failed to get status: {e}")
        results["responses"]["status_initial"] = {"error": str(e)}
        return
    
    # 3. Start VM
    if current_status == 'stopped':
        endpoint_start = f"/nodes/{node}/qemu/{vmid}/status/start"
        print("\n" + "=" * 60)
        print("STARTING VM")
        print(f"Endpoint: POST {endpoint_start}")
        print("=" * 60)
        
        try:
            start_response = proxmox.nodes(node).qemu(vmid).status.start.post()
            results["endpoints"]["start_vm"] = {"method": "POST", "path": endpoint_start}
            results["responses"]["start_vm"] = start_response
            print(json.dumps(start_response, indent=2))
            
            print("\n⏳ Waiting 5 seconds for VM to start...")
            time.sleep(5)
            
            # Check status after start
            status = proxmox.nodes(node).qemu(vmid).status.current.get()
            results["responses"]["status_after_start"] = status
            print(f"📊 Status after start: {status.get('status')}")
        except Exception as e:
            print(f"❌ Failed to start VM: {e}")
            results["responses"]["start_vm"] = {"error": str(e)}
    
    # 4. Stop VM
    endpoint_stop = f"/nodes/{node}/qemu/{vmid}/status/stop"
    print("\n" + "=" * 60)
    print("STOPPING VM")
    print(f"Endpoint: POST {endpoint_stop}")
    print("=" * 60)
    
    try:
        stop_response = proxmox.nodes(node).qemu(vmid).status.stop.post()
        results["endpoints"]["stop_vm"] = {"method": "POST", "path": endpoint_stop}
        results["responses"]["stop_vm"] = stop_response
        print(json.dumps(stop_response, indent=2))
        
        print("\n⏳ Waiting 5 seconds for VM to stop...")
        time.sleep(5)
        
        # Check status after stop
        status = proxmox.nodes(node).qemu(vmid).status.current.get()
        results["responses"]["status_after_stop"] = status
        print(f"📊 Status after stop: {status.get('status')}")
    except Exception as e:
        print(f"❌ Failed to stop VM: {e}")
        results["responses"]["stop_vm"] = {"error": str(e)}
    
    # 5. Get VM Config
    endpoint_config = f"/nodes/{node}/qemu/{vmid}/config"
    print("\n" + "=" * 60)
    print("GET VM CONFIG")
    print(f"Endpoint: GET {endpoint_config}")
    print("=" * 60)
    
    try:
        config = proxmox.nodes(node).qemu(vmid).config.get()
        results["endpoints"]["vm_config"] = {"method": "GET", "path": endpoint_config}
        results["responses"]["vm_config"] = config
        print(json.dumps(config, indent=2))
    except Exception as e:
        print(f"❌ Failed to get config: {e}")
        results["responses"]["vm_config"] = {"error": str(e)}
    
    # 6. Start VM Again (if stopped)
    endpoint_start_again = f"/nodes/{node}/qemu/{vmid}/status/start"
    print("\n" + "=" * 60)
    print("STARTING VM AGAIN")
    print(f"Endpoint: POST {endpoint_start_again}")
    print("=" * 60)
    
    try:
        start_response = proxmox.nodes(node).qemu(vmid).status.start.post()
        results["endpoints"]["start_vm_again"] = {"method": "POST", "path": endpoint_start_again}
        results["responses"]["start_vm_again"] = start_response
        print(json.dumps(start_response, indent=2))
        
        print("\n⏳ Waiting 5 seconds...")
        time.sleep(5)
        
        # Final status check
        status = proxmox.nodes(node).qemu(vmid).status.current.get()
        results["responses"]["status_final"] = status
        print(f"📊 Final Status: {status.get('status')}")
    except Exception as e:
        print(f"❌ Failed to start VM: {e}")
        results["responses"]["start_vm_again"] = {"error": str(e)}
    
    # Save all responses to JSON file
    output_file = Path(__file__).parent / "responses" / f"proxmox_responses_{vmid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print(f"✅ All responses saved to: {output_file}")
    print("=" * 60)

if __name__ == "__main__":
    test_vm_operations()
