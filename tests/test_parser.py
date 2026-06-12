import pytest
from src.bot_app.app.routing.parser import parse_update
from src.bot_app.shared.models.telegram import Update, Message, Chat

def test_parse_valid_command():
    update = Update(
        update_id=100,
        message=Message(
            message_id=1,
            chat=Chat(id=123, type="private"),
            date=1600000000,
            text="/echo hello world"
        )
    )
    
    command = parse_update(update)
    
    assert command.name == "/echo"
    assert command.args == ["hello", "world"]
    assert command.raw_text == "hello world"
    assert command.chat_id == 123
    assert command.update_id == 100

def test_parse_command_no_args():
    update = Update(
        update_id=101,
        message=Message(
            message_id=2,
            chat=Chat(id=456, type="private"),
            date=1600000001,
            text="/ping"
        )
    )
    
    command = parse_update(update)
    
    assert command.name == "/ping"
    assert command.args == []
    assert command.raw_text == ""

def test_parse_invalid_update():
    update = Update(update_id=102, message=None)
    with pytest.raises(ValueError, match="Update contains no message text"):
        parse_update(update)
