from typing import Dict, Any


class OPORDGenerator:
    """Generador de Ordenes de Operaciones segun doctrina OTAN."""

    TEMPLATE = {
        "situation": {"enemy": "", "own": "", "attachments": [], "civilian": ""},
        "mission": "",
        "execution": {"concept": "", "tasks": [], "coordinating_instructions": ""},
        "sustainment": {"logistics": "", "medical": "", "personnel": ""},
        "command_signal": {"command": "", "signal": ""},
    }

    async def generate(self, mission_params: Dict[str, Any]) -> Dict[str, Any]:
        opord = dict(self.TEMPLATE)
        opord["mission"] = mission_params.get("mission", "")
        opord["situation"]["enemy"] = mission_params.get("enemy_situation", "")
        opord["situation"]["own"] = mission_params.get("own_situation", "")
        opord["execution"]["concept"] = mission_params.get("concept", "")
        opord["execution"]["tasks"] = mission_params.get("tasks", [])
        return opord

    async def generate_fragmentary(self, base_opord: Dict, updates: Dict) -> Dict:
        fragord = dict(base_opord)
        for key, value in updates.items():
            if key in fragord:
                fragord[key] = value
        return fragord

    async def validate(self, opord: Dict) -> Dict:
        missing = []
        for section in ["mission", "execution", "sustainment", "command_signal"]:
            if not opord.get(section):
                missing.append(section)
        return {"valid": len(missing) == 0, "missing_sections": missing}


opord_gen = OPORDGenerator()
