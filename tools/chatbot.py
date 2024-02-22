import time
import pytox.toxcore.tox as core


class Chatbot(core.Tox_Ptr):
    running: bool = True

    def handle_self_connection_status(
            self, connection_status: core.Tox_Connection) -> None:
        print(connection_status.name)
        self.running = False



def main() -> None:
    bot = Chatbot()
    bot.bootstrap("tox.abilinski.com", 33445, bytes.fromhex("10C00EB250C3233E343E2AEBA07115A5C28920E9C8D29492F6D00B29049EDC7E"))
    while bot.running:
        bot.iterate()
        time.sleep(0.2)


if __name__ == "__main__":
    main()
