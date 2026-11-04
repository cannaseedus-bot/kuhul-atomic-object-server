#!/usr/bin/env python3
import hashlib
import json
import sys
import time


def process_file(parameters):
    """Example file processing."""
    operation = parameters.get('operation', 'hash')
    content = parameters.get('content', '')

    if operation == 'hash':
        result = hashlib.md5(content.encode()).hexdigest()
    elif operation == 'count':
        result = {
            'characters': len(content),
            'words': len(content.split()),
            'lines': len(content.split('\n'))
        }
    elif operation == 'reverse':
        result = content[::-1]
    else:
        result = None

    return result


if __name__ == "__main__":
    try:
        task_json = sys.stdin.readline().strip()
        task = json.loads(task_json)

        print(f"File worker started for {task['task_id']}", flush=True)
        time.sleep(1)

        result = process_file(task['parameters'])

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
