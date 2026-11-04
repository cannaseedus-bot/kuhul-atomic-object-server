#!/usr/bin/env python3
import json
import sys
import time


def calculate(parameters):
    """Perform calculations."""
    operation = parameters.get('operation')
    a = parameters.get('a', 0)
    b = parameters.get('b', 0)

    operations = {
        'add': lambda x, y: x + y,
        'subtract': lambda x, y: x - y,
        'multiply': lambda x, y: x * y,
        'divide': lambda x, y: x / y if y != 0 else 'undefined',
        'power': lambda x, y: x ** y
    }

    if operation in operations:
        return operations[operation](a, b)
    return None


if __name__ == "__main__":
    try:
        task_json = sys.stdin.readline().strip()
        task = json.loads(task_json)

        print(f"Calculator worker started for {task['task_id']}", flush=True)
        time.sleep(0.5)

        result = calculate(task['parameters'])

        result_data = {
            'task_id': task['task_id'],
            'result': result,
            'status': 'completed'
        }

        print(f"RESULT:{json.dumps(result_data)}", flush=True)

    except Exception as exc:
        error_data = {'error': str(exc)}
        print(f"ERROR:{json.dumps(error_data)}", flush=True)
        sys.exit(1)
