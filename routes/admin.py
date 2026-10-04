from flask import Blueprint, jsonify, request
from commands.interpreter import interpret
from commands.registry import get_command
admin_bp = Blueprint("admin", __name__)
@admin_bp.get("/status")
def admin_status():
    return jsonify({
        "success": True,
        "area": "admin",
        "status": "available"
    })
@admin_bp.post("/command")
def admin_command():
    data = request.get_json(silent=True) or {}
    command = str(data.get("command", "")).strip()
    if not command:
        return jsonify({
            "success": False,
            "error": "Command is required"
        }), 400
    interpreted = interpret(command)
    if not interpreted.get("success"):
        return jsonify(interpreted), 400
    command_type = interpreted["command_type"]
    registered = get_command(command_type)
    if not registered:
        return jsonify({
            "success": False,
            "error": "Command handler not available",
            "command_type": command_type
        }), 500
    result = registered["handler"](
        interpreted.get("parameters", {})
    )
    return jsonify({
        "success": True,
        "command": command,
        "command_type": command_type,
        "parameters": interpreted.get("parameters", {}),
        "result": result
    })
