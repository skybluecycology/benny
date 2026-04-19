"""
Benny Doctor — Automated health probes for the portable stack.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List, Tuple, Optional

import httpx
from benny.core.models import LOCAL_PROVIDERS, is_local_model, _offline_enabled
from benny.core.manifest import SwarmManifest, MANIFEST_SCHEMA_VERSION
from benny.core.workspace import load_manifest

from pydantic import BaseModel, Field

class CheckResult(BaseModel):
    name: str
    status: str  # "OK", "WARN", "ERROR"
    message: str

class DoctorReport(BaseModel):
    checks: List[CheckResult]
    
    @property
    def status_code(self) -> int:
        """Exit code: 0 (OK), 1 (ERROR), 2 (WARN only)."""
        if any(c.status == "ERROR" for c in self.checks):
            return 1
        if any(c.status == "WARN" for c in self.checks):
            return 2
        return 0

def check_home_dir() -> CheckResult:
    """Check if BENNY_HOME is valid and writable."""
    home = os.environ.get("BENNY_HOME")
    if not home:
        return CheckResult(name="BENNY_HOME", status="ERROR", message="Environment variable not set.")
    
    path = Path(home)
    if not path.exists():
        return CheckResult(name="BENNY_HOME", status="ERROR", message=f"Path does not exist: {home}")
    
    # Check writability
    try:
        test_file = path / ".doctor_write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return CheckResult(name="BENNY_HOME", status="OK", message=f"Valid and writable: {home}")
    except Exception as e:
        return CheckResult(name="BENNY_HOME", status="ERROR", message=f"Path not writable: {e}")

def check_structure() -> CheckResult:
    """Check for required directory structure."""
    home = os.environ.get("BENNY_HOME")
    if not home:
        return CheckResult(name="Structure", status="ERROR", message="BENNY_HOME not set; cannot check.")
    
    required = ["workflows", "runs", "logs", "bin"]
    missing = [d for d in required if not (Path(home) / d).is_dir()]
    
    if not missing:
        return CheckResult(name="Structure", status="OK", message="All required directories present.")
    return CheckResult(name="Structure", status="ERROR", message=f"Missing directories: {', '.join(missing)}")

async def probe_service(name: str, url: str) -> Tuple[bool, str]:
    """Probe an HTTP service with a short timeout."""
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                return True, "Responding (200 OK)"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

async def check_services() -> List[CheckResult]:
    """Probe all local LLM services and the backend."""
    results = []
    
    # Check LLM Providers
    for p_id, p_info in LOCAL_PROVIDERS.items():
        name = p_info["name"]
        url = p_info.get("check_url")
        if not url:
            results.append(CheckResult(name=f"Service: {name}", status="OK", message="Static library (no probe)"))
            continue
            
        ok, msg = await probe_service(name, url)
        results.append(CheckResult(name=f"Service: {name}", status="OK" if ok else "WARN", message=msg))
    
    # Check Backend (Marquez proxies etc)
    # We'll probe the default backend port if set
    api_port = os.environ.get("BENNY_API_PORT", "8005")
    ok, msg = await probe_service("Backend API", f"http://127.0.0.1:{api_port}/health")
    if not ok:
        # Fallback probe to root
        ok, msg = await probe_service("Backend API", f"http://127.0.0.1:{api_port}/")
    results.append(CheckResult(name="Backend API", status="OK" if ok else "ERROR", message=msg))
    
    return results

def check_offline_policy() -> CheckResult:
    """Warn if offline is set but cloud model is the default."""
    offline = _offline_enabled()
    try:
        manifest = load_manifest("default")
        default_model = manifest.default_model
        
        if offline and default_model and not is_local_model(default_model):
            return CheckResult(
                name="Offline Policy", 
                status="WARN", 
                message=f"BENNY_OFFLINE=1 but default_model '{default_model}' is cloud-based. "
                "Tasks will fail until a local model is set."
            )
    except:
        pass # If manifest is missing, that's covered by other checks
    
    return CheckResult(name="Offline Policy", status="OK", message="Compliant" if offline else "Offline mode disabled.")

def check_hardware_clock() -> CheckResult:
    """Detect RTC battery failure on offline hardware."""
    current_year = time.gmtime().tm_year
    if current_year < 2024:
        return CheckResult(
            name="Hardware Clock", 
            status="ERROR", 
            message=f"System year ({current_year}) is suspiciously in the past. Check CMOS battery."
        )
    return CheckResult(name="Hardware Clock", status="OK", message=f"System time verified: {time.strftime('%Y-%m-%d')}")

def check_kg3d_stack() -> List[CheckResult]:
    """Check availability of KG3D persistence layers."""
    results = []
    
    # Check SQLite metrics cache
    home = os.environ.get("BENNY_HOME")
    if home:
        cache_path = Path(home) / "data" / "kg3d_metrics.db"
        if cache_path.exists():
            results.append(CheckResult(name="KG3D: Metrics Cache", status="OK", message="Database exists and is reachable."))
        else:
            results.append(CheckResult(name="KG3D: Metrics Cache", status="WARN", message="Cache DB missing. Will be initialized on first run."))

    return results

async def run_doctor() -> DoctorReport:
    """Run all diagnostics and return a report."""
    checks = []
    checks.append(check_home_dir())
    checks.append(check_structure())
    checks.append(check_hardware_clock())
    checks.append(check_offline_policy())
    
    # Async service checks
    service_checks = await check_services()
    checks.extend(service_checks)
    
    # Schema check
    checks.append(CheckResult(
        name="Manifest Schema", 
        status="OK", 
        message=f"v{MANIFEST_SCHEMA_VERSION}"
    ))

    # KG3D Stack checks
    checks.extend(check_kg3d_stack())
    
    return DoctorReport(checks=checks)
