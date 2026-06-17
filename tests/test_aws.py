"""
Uji koneksi & control-plane AWS (boto3) untuk AWSProvider.

Bertahap:
  # (1) Uji kredensial + config — GRATIS, tidak melaunch instance:
  python tests/test_aws.py

  # (2) Uji penuh control-plane — launch instance kecil, cek port SSH, lalu TERMINATE.
  #     Ada biaya kecil (t3.micro, beberapa menit). Pastikan terminasi jalan.
  python tests/test_aws.py --launch
"""
import argparse
import os
import socket
import sys
import time

import boto3

# Pastikan root project ada di sys.path (saat skrip dijalankan langsung dari tests/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings


def _kwargs():
    return dict(
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )


def check_creds(ec2) -> bool:
    print(f"[1] Region          : {settings.AWS_REGION}")
    try:
        ident = boto3.client("sts", **_kwargs()).get_caller_identity()
        print(f"    IAM identity    : OK (account={ident['Account']})")
        print(f"                      {ident['Arn']}")
    except Exception as e:
        print(f"    IAM identity    : GAGAL → {e}")
        return False
    try:
        res = ec2.describe_instances()
        print(f"    describe_instances: OK ({len(res.get('Reservations', []))} reservations)")
    except Exception as e:
        print(f"    describe_instances: GAGAL → {e}")
        return False

    print("    Config penting   :")
    ok = True
    for k in ["AWS_AMI_ID", "AWS_INSTANCE_TYPE", "AWS_SECURITY_GROUP_ID",
              "AWS_KEY_PAIR_NAME", "AWS_SSH_USER", "AWS_SSH_KEY_PATH"]:
        v = getattr(settings, k, "")
        flag = "" if v else "  ← KOSONG!"
        if not v and k in ("AWS_AMI_ID", "AWS_KEY_PAIR_NAME"):
            ok = False
        print(f"      {k:24} = {v}{flag}")
    return ok


def launch_test(ec2) -> None:
    print("\n[2] Launch test instance (akan di-terminate di akhir)...")
    run_kwargs = {
        "ImageId": settings.AWS_AMI_ID,
        "InstanceType": settings.AWS_INSTANCE_TYPE,
        "MinCount": 1, "MaxCount": 1,
        "TagSpecifications": [{
            "ResourceType": "instance",
            "Tags": [{"Key": "Name", "Value": "ctf-aws-test"}],
        }],
    }
    if settings.AWS_KEY_PAIR_NAME:
        run_kwargs["KeyName"] = settings.AWS_KEY_PAIR_NAME
    if settings.AWS_SUBNET_ID:
        run_kwargs["SubnetId"] = settings.AWS_SUBNET_ID
    if settings.AWS_SECURITY_GROUP_ID:
        run_kwargs["SecurityGroupIds"] = [settings.AWS_SECURITY_GROUP_ID]

    iid = ec2.run_instances(**run_kwargs)["Instances"][0]["InstanceId"]
    print(f"    launched        : {iid}")
    try:
        print("    waiting running ...")
        ec2.get_waiter("instance_running").wait(InstanceIds=[iid])
        inst = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]
        ip = inst.get("PublicIpAddress")
        print(f"    public IP       : {ip}")
        if not ip:
            print("    ⚠️ tidak dapat public IP — cek subnet/auto-assign public IP")
            return

        # ── Diagnostik jaringan ──────────────────────────────────────────────
        import urllib.request
        try:
            my_ip = urllib.request.urlopen("https://checkip.amazonaws.com", timeout=5).read().decode().strip()
            print(f"    egress IP (ini) : {my_ip}  (harus cocok dgn source rule 22, atau pakai 0.0.0.0/0)")
        except Exception:
            pass
        sgs = inst.get("SecurityGroups", [])
        print(f"    SG ter-attach   : {[s['GroupId'] for s in sgs]}")
        for s in sgs:
            g = ec2.describe_security_groups(GroupIds=[s["GroupId"]])["SecurityGroups"][0]
            for p in g.get("IpPermissions", []):
                ranges = [r.get("CidrIp") for r in p.get("IpRanges", [])]
                print(f"      ingress {p.get('IpProtocol')} port {p.get('FromPort')}-{p.get('ToPort')} from {ranges}")
        subnet_id = inst.get("SubnetId")
        print(f"    subnet          : {subnet_id}")

        print("    waiting status checks (SSH siap) ...")
        ec2.get_waiter("instance_status_ok").wait(InstanceIds=[iid])
        reachable = False
        for _ in range(12):
            try:
                with socket.create_connection((ip, 22), timeout=5):
                    reachable = True
                    break
            except OSError:
                time.sleep(5)
        print(f"    SSH port 22     : {'REACHABLE ✓' if reachable else 'TIDAK reachable ✗ (cek SG izinkan 22)'}")
    finally:
        print(f"    terminating     : {iid} ...")
        ec2.terminate_instances(InstanceIds=[iid])
        print("    terminated (cek di console pastikan benar-benar hilang).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--launch", action="store_true", help="launch instance nyata lalu terminate (ada biaya kecil)")
    args = ap.parse_args()

    ec2 = boto3.client("ec2", **_kwargs())
    ok = check_creds(ec2)
    if not ok:
        print("\n→ Perbaiki config yang KOSONG/GAGAL dulu sebelum --launch.")
        return
    if args.launch:
        launch_test(ec2)
    else:
        print("\n→ Kredensial & config OK. Tambah '--launch' untuk uji launch+SSH+terminate.")


if __name__ == "__main__":
    main()
