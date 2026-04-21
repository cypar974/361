import sqlite3

def clean_template():
    conn = sqlite3.connect("default.db")
    cursor = conn.cursor()

    # Clear out any accidental save data
    tables_to_clear = ["game_sessions", "player_state", "session_world_state", "inventory"]
    for table in tables_to_clear:
        cursor.execute(f"DELETE FROM {table}")

    conn.commit()
    conn.close()
    print("Successfully sanitized default.db! Map data is fully intact.")

if __name__ == "__main__":
    clean_template()
