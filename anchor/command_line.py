import sys

from montreal_forced_aligner import config
from montreal_forced_aligner.helper import configure_logger

from anchor.main import Application, MainWindow


def main(debug=False):
    configure_logger("anchor")
    configure_logger("anchor", config.TEMPORARY_DIRECTORY.joinpath("anchor.log"))

    app = Application(sys.argv)
    main = MainWindow(debug=debug)

    app.setActiveWindow(main)
    main.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
