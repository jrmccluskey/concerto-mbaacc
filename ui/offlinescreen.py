from ui.concertoscreen import ConcertoScreen
from ui.modals import GameModal, ChoiceModal, ProgressModal
from ui.downloads import download_etm, EtmDownloadError
from kivy.clock import Clock
from functools import partial
import threading
import logging
import os
import config
import ui.lang
from ui.playerwiki import *

class OfflineScreen(ConcertoScreen):
    
    def __init__(self,CApp):
        super().__init__(CApp)
        self.etm_downloading = False # True while Extended Training Mode is being downloaded
        self.etm_last_progress_step = None # last progress step pushed to the UI

    def training(self, *args):
        self.offline_pop(ui.lang.localize("OFFLINE_MENU_TRAINING"),tip=ui.lang.localize("TIP_CONTROLS"))
        caster = threading.Thread(target=self.app.game.training,args=[self],daemon=True)
        caster.start()

    def extended_training(self, *args):
        if self.etm_downloading:
            return None
        if os.path.isfile(config.PATH + config.ETM_EXE_NAME):
            self.launch_extended_training()
        else:
            self.prompt_etm_download()

    def prompt_etm_download(self):
        popup = ChoiceModal(ui.lang.localize("ETM_DOWNLOAD_PROMPT"),
            btn1txt=ui.lang.localize("TERM_CANCEL"),
            btn2txt=ui.lang.localize("TERM_DOWNLOAD"))
        popup.btn_1.bind(on_release=self.dismiss_active_pop)
        popup.btn_2.bind(on_release=self.start_etm_download)
        popup.open()
        self.active_pop = popup

    def start_etm_download(self, *args):
        self.dismiss_active_pop()
        self.etm_downloading = True
        self.etm_last_progress_step = None
        popup = ProgressModal()
        popup.modal_txt.text = ui.lang.localize("ETM_CHECKING")
        popup.prog_bar.max = 100
        popup.prog_bar.value = 0
        popup.open()
        self.active_pop = popup
        threading.Thread(target=self.etm_download_worker,daemon=True).start()

    def etm_download_worker(self):
        try:
            tag = download_etm(config.PATH, config.ETM_RELEASES_API, config.ETM_EXE_NAME,
                config.ETM_TAG_PATTERN, progress_cb=self.etm_download_progress)
        except EtmDownloadError as e:
            Clock.schedule_once(partial(self.etm_download_done, None, str(e)))
        except Exception as e: # never leave the progress modal stuck open
            logging.warning('Concerto: Extended Training Mode download error: %s' % e)
            Clock.schedule_once(partial(self.etm_download_done, None, str(e)))
        else:
            Clock.schedule_once(partial(self.etm_download_done, tag, None))

    def etm_download_progress(self, tag, received, total):
        # called from the download thread, so marshal UI updates onto the main thread.
        # throttled to whole-percent changes to avoid flooding the Clock with events.
        step = int(received * 100 / total) if total else received // (1024 * 1024)
        if step == self.etm_last_progress_step and received != total:
            return
        self.etm_last_progress_step = step
        Clock.schedule_once(partial(self.update_etm_progress, tag, received, total))

    def update_etm_progress(self, tag, received, total, *args):
        if isinstance(self.active_pop, ProgressModal):
            if total:
                percent = round(float(received) / total * 100, 2)
                self.active_pop.prog_bar.value = percent
            else:
                percent = 0
                total = '?'
            self.active_pop.modal_txt.text = ui.lang.localize("ETM_DOWNLOADING", (tag, received, total, percent))

    def etm_download_done(self, tag, err, *args):
        self.etm_downloading = False
        self.dismiss_active_pop()
        if err:
            self.error_message(ui.lang.localize("ETM_DOWNLOAD_FAIL", err))
        else:
            logging.info('Concerto: downloaded Extended Training Mode %s' % tag)
            self.launch_extended_training()

    def launch_extended_training(self):
        self.offline_pop(ui.lang.localize("OFFLINE_MENU_EXTENDED_TRAINING"),tip=ui.lang.localize("TIP_EXTENDED_TRAINING"))
        caster = threading.Thread(target=self.app.game.extended_training,args=[self],daemon=True)
        caster.start()

    def replays(self, *args):
        self.offline_pop(ui.lang.localize("OFFLINE_MENU_REPLAYS"))
        caster = threading.Thread(target=self.app.game.replays,args=[self],daemon=True)
        caster.start()
    
    def trials(self, *args):
        self.offline_pop(ui.lang.localize("OFFLINE_MENU_TRIALS"),tip=ui.lang.localize("TIP_TRIALS"))
        caster = threading.Thread(target=self.app.game.trials,args=[self],daemon=True)
        caster.start()

    def local(self, *args):
        self.offline_pop(ui.lang.localize("OFFLINE_MENU_LOCAL_VS"),tip=ui.lang.localize("TIP_CONTROLS"))
        caster = threading.Thread(target=self.app.game.local,args=[self],daemon=True)
        caster.start()

    def cpu(self, *args):
        self.offline_pop(ui.lang.localize("OFFLINE_MENU_CPU_VS"),tip=ui.lang.localize("TIP_CONTROLS"))
        caster = threading.Thread(target=self.app.game.cpu,args=[self],daemon=True)
        caster.start()

    def tournament(self, *args):
        self.offline_pop("Tournament VS",tip=ui.lang.localize("TIP_PAUSE"))
        caster = threading.Thread(target=self.app.game.tournament,args=[self],daemon=True)
        caster.start()

    def standalone(self, *args):
        self.offline_pop("Standalone")
        caster = threading.Thread(target=self.app.game.standalone,args=[self],daemon=True)
        caster.start()

    def offline_pop(self, mode, tip=""):
        self.app.offline_mode = mode
        popup = GameModal(ui.lang.localize('OFFLINE_MENU_STARTING') % (mode,tip),ui.lang.localize('TERM_STANDBY'))
        popup.close_btn.disabled = True
        popup.remove_widget(popup.p1_char_guide)
        popup.remove_widget(popup.p2_char_guide)
        popup.open()
        self.active_pop = popup
        