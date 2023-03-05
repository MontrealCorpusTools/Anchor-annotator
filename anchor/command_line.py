import sys
import os
from anchor.main import MainWindow, Application
from montreal_forced_aligner.command_line.utils import check_databases
from montreal_forced_aligner.config import MFA_PROFILE_VARIABLE, GLOBAL_CONFIG
from montreal_forced_aligner.helper import configure_logger


def main(debug=False):
    os.environ[MFA_PROFILE_VARIABLE] = "anchor"
    GLOBAL_CONFIG.profiles['anchor'].clean = False
    GLOBAL_CONFIG.save()
    configure_logger('anchor')
    configure_logger('anchor', GLOBAL_CONFIG.current_profile.temporary_directory.joinpath('anchor.log'))
    check_databases(db_name='anchor')
    app = Application(sys.argv)
    main = MainWindow(debug=debug)

    app.setActiveWindow(main)
    main.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()