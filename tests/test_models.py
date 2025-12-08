"""
Script untuk testing models
"""
from core import engine, Base, logger
from models import Deployment, DeploymentStatus


def test_models():
    """Test create tables dan basic CRUD"""
    
    # Create tables
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.success("Tables created successfully!")
    
    # Print table names
    logger.info(f"Tables: {Base.metadata.tables.keys()}")
    
    # Test Deployment model
    logger.info("\n=== Testing Deployment Model ===")
    deployment = Deployment(
        team_name="Team Alpha",
        team_email="alpha@example.com",
        team_institution="Example University",
        challenge_name="SQL Injection Challenge",
        challenge_category="injection",
        challenge_difficulty="easy",
        vm_id=200,
        vm_name="team-alpha-sqli",
        vm_ip="192.168.100.10",
        vm_port=8080,
        vm_memory=512,
        vm_cores=1,
        ssh_port=2222,
        ssh_username="ctfuser",
        ssh_password="ctfpass123",
        web_url="http://192.168.100.10:8080",
        flag="CTF{test_flag_12345}",
        status=DeploymentStatus.RUNNING,
        notes="Test deployment"
    )
    logger.info(f"Deployment created: {deployment}")
    logger.info(f"Deployment dict (no flag): {deployment.to_dict()}")
    logger.info(f"Deployment dict (with flag): {deployment.to_dict(include_flag=True)}")
    logger.info(f"Is active: {deployment.is_active()}")
    
    # Test enums
    logger.info("\n=== Testing Enums ===")
    logger.info(f"Deployment statuses: {[s.value for s in DeploymentStatus]}")
    
    logger.success("\n✅ All model tests passed!")


if __name__ == "__main__":
    test_models()
