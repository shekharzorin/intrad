from agents.auth_agent import AuthAgent

alice = AuthAgent().login()
print('TYPE:', type(alice))
print('HAS start_websocket:', hasattr(alice, 'start_websocket'))
print('HAS subscribe:', hasattr(alice, 'subscribe'))
print('DIRECTORY:')
for a in sorted([a for a in dir(alice) if not a.startswith('_')]):
    print(' -', a)

# Print the implementations for key methods if present
for name in ['start_websocket','subscribe','connect','disconnect','start_websocket_for_token','connect_websocket']:
    if hasattr(alice, name):
        print(f"\nDETAIL: {name} -> {getattr(alice, name)}")
