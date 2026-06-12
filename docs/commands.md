# Commands

Commands are the primary way users interact with the bot. This boilerplate follows a strict registration pattern to ensure all commands are documented and discoverable.

## Command Registry
All commands must be registered in `src/bot_app/app/routing/command_registry.py`. This registry acts as the Single Source of Truth for:
- Command name (e.g., `/ping`)
- Description (used for `/help`)
- Handler mapping

## Default Commands

### Basic
- `/ping`: Responds with "alive". Used to check if the bot is running.
- `/echo <text>`: Repeats the provided text.
- `/help`: Dynamically generates a list of available commands and their descriptions.

### Notes
- `/note <text>`: Saves a new note for the current user.
- `/notes`: Lists the 10 most recent notes saved by the user.

## Adding a New Command
1. Create a new feature module in `src/bot_app/features/`.
2. Implement the handler function.
3. Add the command and its handler to the `CommandRegistry`.
4. Update services or repositories if the command requires persistence or external logic.
