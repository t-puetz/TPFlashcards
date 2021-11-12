import tkinter as tk
import tkinter.font as tkFont
import os
import csv
import sys
import threading
import time
import re
import random
import platform
import argparse
import subprocess

ffplay_pids = []

def constructAndGetArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--path-to-deck", help="Path to deck and also important for prepending path to sound file", required=False)
    parser.add_argument("-f", "--font", help="Name of a font family installed on your system", required=False)
    parser.add_argument("-n", "--font-name", help="Name of a font installed on your system", required=False)
    parser.add_argument("-t", "--font-style", choices=['bold', 'normal'], help="bold or normal", required=False)
    parser.add_argument("-z", "--font-size", help="Well, the font size", required=False)
    parser.add_argument("-s", "--shuffle", action='store_true', help="If specified deck will be shuffled at start", required=False)
    parser.add_argument("-r", "--remove-duplicates", action='store_true', help="Remove duplicates before loading CSV into memory", required=False)
    parser.add_argument("-l", "--fliptime", type=float, help="Time in seconds (may be a float) to flip a card.", required=False)
    parser.add_argument("-w", "--switchtime", type=float, help="Time in seconds (may be a float) to switch between two cards", required=False)
    parser.add_argument("-u", "--path-to-ffplay", help="Path to ffplay binary including the binary itself.", required=False)

    args = parser.parse_args()
    return args

def isUrl(string):
    regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
    url = re.findall(regex, string)
    found_urls = [x[0] for x in url]
    return (len(found_urls) > 0)

class Flashcard():
    def __init__(self, _id, frontside_labeltext, backside_labeltext, soundfile):
        # We assume the frontside holds the content you know
        # such as your mother language
        # The backside holds the stuff you want to learn, the foreign language
        # There there is only one soundfile member
        # because it should play what is on the backside (the foreign language)
        self.id = int(_id)
        self.frontside_labeltext = frontside_labeltext
        self.backside_labeltext = backside_labeltext
        self.soundfile = soundfile
        self.cur_side = 'front'

class Deck():
    def __init__(self):
        self.cards = {}

class FlashcardsApp(tk.Frame):
    def __init__(self, master, geometry, name, version, bgcolor, path_csv_deck, os, args):
        super().__init__(master)
        self.pack()
        self.bgcolor = bgcolor
        self.master = master
        self.master.resizable(False, False)
        self.geometry = geometry
        self.name = name
        self.version = version
        self.path_csv_deck = path_csv_deck
        self.os = os
        self.args = args
        self.master.configure(bg=self.bgcolor)
        self.configure(bg=self.bgcolor)

        self.title = f'{name} v{version}'
        self.cur_flashcard_side = 'front'
        self.cur_card = None
        self.deck = None
        self.validatecmd_goto_input = None
        self.sndfile_basepath = self.args.path_to_deck[:self.args.path_to_deck.rfind('/')]
        self.path_ffplay = self.getPathFfplay()

        self.font = self.args.font if self.args.font else 'roman'
        self.font_style = self.args.font_style if self.args.font_style  else 'bold'
        self.font_size = self.args.font_size if self.args.font_size else '22'
        self.font_name = self.args.font_name if self.args.font_name else 'IDoNotExist'

        self.autoflip = tk.IntVar()
        self.autowalk = tk.IntVar()
        self.autoflip_thread = None

        self.fliptime = 4.0 if not self.args.fliptime else self.args.fliptime
        self.switchtime = 3.0 if not self.args.switchtime else self.args.switchtime

        # The user may choose, however nothing under 2.0 seconds
        # we create a lower limit it gets capped to here
        self.fliptime = 2.0 if self.fliptime < 2.0 else self.fliptime
        self.switchtime = 2.0 if self.switchtime < 2.0 else self.switchtime

        # Prematurely setup dict that will hold all future widgets once created
        # by self.createWidgets()
        # mainframe: LabelFrame representing the rectangular body of a flashcard
        # label: The actual text of the current flashcards (both front or backside)
        # there is just ever ONE label. Just the text of that label gets updated!
        self.widgets = {'supermaster': self, 'master': self.master,
                        'mainframe': None, 'label': None, 'fwd_btn': None,
                        'jmp_end_btn': None, 'bwd_btn': None, 'jmp_start_btn': None,
                        'flp_btn': None, 'snd_btn': None, 'goto_input': None,
                        'autoflip_chkbtn': None, 'autowalk_chkbtn': None, 'card_in_deck_pos': None}

        # --------------------------------
        # Start of creating widget configs
        # --------------------------------
        # Prematurely sets up config dicts that when used
        # will be double unwrapped using **
        # to provide kwargs to respective widget constructors
        self.mainframe_config = {'bg': '#707070', 'width': 900, 'height': 500}

        self.flashcard_font = tkFont.Font(name=self.args.font_name, family=self.args.font, size=self.args.font_size, weight=self.args.font_style, slant='roman')
       # print(f"tkFont.names():\n{tkFont.names()}")
       # print(f"tkFont.families():\n{tkFont.families()}")

        self.flashcard_config = {'text': 'No data loaded', 'wraplength': 450,
                                 'bg': '#707070', 'fg': 'white', 'height': 10,
                                 'width': 24, 'font': self.flashcard_font}
        self.snd_btn_config = {'text': '   🔊   ', 'command': lambda: self.playBacksideSound(self.cur_card)}
        self.fwd_btn_config = {'text': '  >>  ', 'command': lambda: self.navigateFlashcards('forward')}
        self.jmp_end_btn_config = {'text': '  >>|  ', 'command': lambda: self.navigateFlashcards('jmp_end')}
        self.bwd_btn_config = {'text': '  <<  ', 'command': lambda: self.navigateFlashcards('backward')}
        self.jmp_start_btn_config = {'text': '  |<<  ', 'command': lambda: self.navigateFlashcards('jmp_start')}
        self.flp_btn_config = {'text': 'F L I P', 'command': lambda: self.flipFlashcard()}
        self.goto_input_config = {'validate': 'key'}
        self.autoflip_chkbtn_config = {'text': 'Auto flip', 'variable': self.autoflip, 'command': lambda: self.autoflipEntryPoint()}
        self.autowalk_chkbtn_config = {'text': 'Auto walk', 'variable': self.autowalk, 'command': lambda: self.autoflipEntryPoint()}

        front_card_indicator = tkFont.Font(size=10, weight='bold', slant='roman')
        self.card_in_deck_pos_config = {'text': '0/0', 'font': front_card_indicator}
        # ------------------------------
        # End of creating widget configs
        # ------------------------------

        # Call some methods while initializing
        # DO NOT CREATE more members/attributes/properties after here
        # They will not get recognized!
        self.setWindowTitle()
        self.setWindowGeometry()
        self.registerOnExitCloseAutoflipThread()
        self.createWidgets()

    def getPathFfplay(self):
        if not self.args.path_to_ffplay:
            if self.os == 'Windows':
                return 'C:/ffmpeg/bin/ffplay.exe'
            else:
                get_path_ffplay = subprocess.run('whereis ffplay | cut -d" " -f2 | tr -d "\n" | tr -d "\n\r"', shell=True, text=True, capture_output=True)
                path_ffplay = get_path_ffplay.stdout if not get_path_ffplay.stderr else '/usr/bin/ffplay'
                return path_ffplay
        else:
            return self.args.path_to_ffplay

    def prependSoundBasePathCsv(self, preliminary_deck):
        if self.sndfile_basepath:
            for pre_card in preliminary_deck.values():
                last_item_index = len(pre_card) - 1
                sndfile_fullpath = ''
                sndfile_is_url = isUrl(pre_card[last_item_index])

                if self.sndfile_basepath.endswith('/') and not sndfile_is_url:
                    sndfile_fullpath = f'{self.sndfile_basepath}{pre_card[last_item_index]}'
                elif not self.sndfile_basepath.endswith('/') and not sndfile_is_url:
                    sndfile_fullpath = f'{self.sndfile_basepath}/{pre_card[last_item_index]}'

                if sndfile_fullpath:
                    pre_card[last_item_index] = sndfile_fullpath

        return preliminary_deck

    def preloadDeck(self):
        preliminary_deck = {}

        with open(self.path_csv_deck, 'r', encoding='utf8') as csvfile:
            reader = csv.reader(csvfile, delimiter=';')
            rowcounter = 0

            for row in reader:
                # Skip CSV header
                if row[0] == 'id':
                    continue

                rowcounter += 1
                preliminary_deck[f'card_{rowcounter}'] = row

        preliminary_deck = self.prependSoundBasePathCsv(preliminary_deck)
        preliminary_deck = self.decideToShufflePrelimDeckOrNot(preliminary_deck)
        preliminary_deck = self.decideToEemoveDuplicatesPrelimDeckOrNot(preliminary_deck)

        return preliminary_deck

    def decideToEemoveDuplicatesPrelimDeckOrNot(self, preliminary_deck):
        if not self.args.remove_duplicates:
            return preliminary_deck

        card_texts_to_check_for_duplicates = []
        duplicate_card_map = {}

        # Combine front and backside (only roman writing) to make a unique string
        # Put the card number in front of the string to store the position so we now
        # what to remove later
        # The second half after '|||' without the card number is our indicator:
        # if it exists more than once we have a duplicate

        # Create a list of those indicator strings
        for key in preliminary_deck:
             flashcard_text = preliminary_deck[key]
             frontside_text = flashcard_text[1]
             backside_text = flashcard_text[2]
             backside_text_no_nonroman_writing = ''

             if backside_text.find('----') > 0:
                 backside_text_no_nonroman_writing = flashcard_text[2].split('----')[1]
             else:
                 backside_text_no_nonroman_writing = flashcard_text[2]

             str_to_check = f'{key}' + '|||' + frontside_text + '||' + backside_text_no_nonroman_writing
             card_texts_to_check_for_duplicates.append(str_to_check)


        # Identify matches as duplicates (only if card number is not the same)
        # Make the string the key of a duplicate map dict and the card number the value
        for key, val in preliminary_deck.items():
            flashcard_text = preliminary_deck[key]
            frontside_text = flashcard_text[1] 
            backside_text = flashcard_text[2]
            backside_text_no_nonroman_writing = ''

            if backside_text.find('----') > 0:
                backside_text_no_nonroman_writing = flashcard_text[2].split('----')[1]
            else:
                backside_text_no_nonroman_writing = flashcard_text[2]

            str_to_check = f'{key}' + '|||' + frontside_text + '||' + backside_text_no_nonroman_writing

            for element in card_texts_to_check_for_duplicates:
                val1 = element.split('|||')[1]
                card1 = element.split('|||')[0]
                val2 = str_to_check.split('|||')[1]
                card2 = str_to_check.split('|||')[0]

                if val1 == val2 and card1 != card2:
                    dupmapkey = f'{val1}::::{val2}'

                    try:
                        duplicate_card_map[dupmapkey]
                    except KeyError:
                        duplicate_card_map[dupmapkey] = []

                    duplicate_card_map[dupmapkey].append(card1)
                    duplicate_card_map[dupmapkey].append(card2)

        # Just to be sure filter out duplicate card numbers per key-val pair
        # Now loop over the card numbers for each flashcard duplicate
        # except for one element and delete all the others from the preliminary deck
        # so all dups except one are removed.
        for key, val in duplicate_card_map.items():
            duplicate_card_map[key] = list(set(duplicate_card_map[key]))
            newval = duplicate_card_map[key]
            counter = 1

            while counter < len(newval):
                del preliminary_deck[newval[counter]]
                counter += 1


        dedupped_prelim_dict = {}

        # Straighten out the card numbers and IDs again
        # assign everything to a new dict because otherwise
        # the original's dict size would change during iteration
        # and python would crash
        counter = 1
        for key, val in preliminary_deck.items():
            val[0] = counter
            dedupped_prelim_dict[f'card_{counter}'] = val
            counter += 1

        # Delete the unduped dict and return the clean one :)
        del preliminary_deck
        return dedupped_prelim_dict

    def decideToShufflePrelimDeckOrNot(self, unshuffled_prelim_deck):
        try:
            if self.args.shuffle:
                shuffled_prelim_dict = {}
                list_keys_prelim_deck = list(unshuffled_prelim_deck.keys())
                random.shuffle(list_keys_prelim_deck)
                counter = 0

                for shuffledkey in list_keys_prelim_deck:
                    new_val = unshuffled_prelim_deck[shuffledkey]
                    new_val[0] = counter+1
                    shuffled_prelim_dict[f'card_{counter+1}'] = new_val
                    counter += 1

                del(unshuffled_prelim_deck)
                return shuffled_prelim_dict
        except IndexError:
            return unshuffled_prelim_deck
        else:
            return unshuffled_prelim_deck

    def loadDeck(self):
        deck = Deck()
        preliminary_deck = self.preloadDeck()

        for pre_card_key, pre_card_content in preliminary_deck.items():
            _id = pre_card_content[0]
            frontside = pre_card_content[1]
            backside = pre_card_content[2]
            soundfile = pre_card_content[3]
            deck.cards[pre_card_key] = Flashcard(_id, frontside, backside, soundfile)

        del(preliminary_deck)
        self.deck = deck

    def setWindowTitle(self):
        self.master.title(self.title)

    def setWindowGeometry(self):
        self.master.geometry(self.geometry)

    def flipFlashcard(self):
        self.widgets['label']['text'] = self.cur_card.backside_labeltext if self.cur_card.cur_side == 'front' else self.cur_card.frontside_labeltext
        self.cur_card.cur_side = 'back' if self.cur_card.cur_side == 'front' else 'front'
        self.cur_flashcard_side = 'back' if self.cur_card.cur_side == 'front' else 'front'
        self.widgets['label'].update()

        self.playBacksideSound(self.cur_card)

    def navigateFlashcards(self, direction):
        cur_card_id = self.cur_card.id
        valid_card_keys = [key for key in list(self.deck.cards.keys())]
        valid_card_ids = list(map(lambda x: int(x[5:]), valid_card_keys))
        index_cur_id_in_valid_ids = valid_card_ids.index(cur_card_id)

        card_to_navigate_to = None
        id_card_to_nav_to = -1

        if direction == 'forward':
            id_card_to_nav_to = cur_card_id + 1 if index_cur_id_in_valid_ids != len(valid_card_ids) - 1 else 1
        elif direction == 'backward':
            id_card_to_nav_to = cur_card_id - 1 if index_cur_id_in_valid_ids != 0 else len(valid_card_ids)
        elif direction == 'jmp_end':
            id_card_to_nav_to = len(self.deck.cards)
        elif direction == 'jmp_start':
            id_card_to_nav_to = 1

        card_to_navigate_to = self.deck.cards[f'card_{id_card_to_nav_to}']

        if card_to_navigate_to:
            self.widgets['label']['text'] = card_to_navigate_to.frontside_labeltext
            self.widgets['label'].update()
            self.cur_card = card_to_navigate_to
            self.cur_flashcard_side = 'front'
            self.deck.cur_card = card_to_navigate_to
            self.deck.cur_side = 'front'
            self.widgets['card_in_deck_pos']['text'] = f'{self.deck.cur_card.id}/{len(valid_card_ids)}'

    def gotoFlashcards(self, text):
        if not text:
            return None

        valid_card_keys = [key for key in list(self.deck.cards.keys())]
        valid_card_ids = list(map(lambda x: int(x[5:]), valid_card_keys))

        try:
            text = int(text)
        except ValueError:
            return None
        except TypeError:
            # Event was sent because Enter was pressed
            # In this case the text is not being send
            # by the callback substitution code '%S'
            # that are provided by self.register()
            # when the validatecommand was registered
            # So we just have to get the text input by
            # using <this_widget>.get()

            try:
                text = int(self.widgets["goto_input"].get())
            except ValueError:
                return None

        if text in valid_card_ids:
            card_to_navigate_to = self.deck.cards[f'card_{text}']
        else:
            return None

        if card_to_navigate_to:
            self.widgets['label']['text'] = card_to_navigate_to.frontside_labeltext
            self.widgets['label'].update()
            self.cur_card = card_to_navigate_to
            self.cur_flashcard_side = 'front'
            self.deck.cur_card = card_to_navigate_to
            self.deck.cur_side = 'front'
            self.widgets['card_in_deck_pos']['text'] = f'{self.deck.cur_card.id}/{len(valid_card_ids)}'

    def playBacksideSound(self, flashcard):
        sndfile = flashcard.soundfile

        if sndfile:
            sndfile_is_url = isUrl(sndfile)
            file_is_on_filesystem = os.path.exists(sndfile)

            if flashcard.cur_side == 'back' and (sndfile_is_url or file_is_on_filesystem):

                if self.os != 'Windows':
                    cmd = f'sh -c "echo $$; exec {self.path_ffplay} -autoexit -vn -nodisp {sndfile} &> /dev/null &"&'
                    ffplay_pid = -1

                    if not ffplay_pids:
                        ffplay_pid = int(subprocess.run(cmd, shell=True, text=True, capture_output=True).stdout.split('\n')[0]) + 2
                        ffplay_pids.append(ffplay_pid)
                    else:
                        pgrep_ffplay = subprocess.run(f'pgrep ffplay', shell=True, text=True, capture_output=True).stdout.split('\n')
                        pgrep_ffplay = list(filter(lambda x: x, pgrep_ffplay))
                        ffplay_still_running = (str(ffplay_pids[0]) in pgrep_ffplay)

                        if ffplay_still_running:
                            os.system(f'kill {ffplay_pids[0]}')
                            ffplay_pids.pop()
                            ffplay_pid = int(subprocess.run(cmd, shell=True, text=True, capture_output=True).stdout.split('\n')[0]) + 2
                            ffplay_pids.append(ffplay_pid)
                        else:
                            ffplay_pids.pop()
                            ffplay_pid = int(subprocess.run(cmd, shell=True, text=True, capture_output=True).stdout.split('\n')[0]) + 2
                            ffplay_pids.append(ffplay_pid)
                else:
                    if self.os == 'Windows':
                        cmd = f'{self.path_ffplay} -autoexit -vn -nodisp {sndfile}'
                        os.system(cmd)

    def initCardCounter(self):
        valid_card_keys = [key for key in list(self.deck.cards.keys())]
        valid_card_ids = list(map(lambda x: int(x[5:]), valid_card_keys))
        self.widgets['card_in_deck_pos']['text'] = f'{self.cur_card.id}/{len(valid_card_ids)}'

    def onExitCloseAutoflipThread(self):
        print('onExitCloseThread()')
        if isinstance(self.autoflip_thread, threading.Thread):
            print('Closing thread...')
            self.autoflip.set(False)
            self.autowalk.set(False)

            if self.widgets['autowalk_chkbtn']['state'] == "normal" and not self.autowalk.get():
                self.master.destroy()

                for widget in self.widgets:
                    if widget != 'supermaster' and widget != 'master':
                        self.widgets[widget].destroy()
                        print("Joining thread")

                print("Joining thread")
                self.autoflip_thread.join()
            elif self.widgets['autoflip_chkbtn']['state'] == "normal" and not self.autoflip.get():
                self.autoflip_thread.join()
        else:
            print('No need to close autoflip thread on Exit')

        self.master.destroy()

    def registerOnExitCloseAutoflipThread(self):
        print('Registering: self.master.protocol("WM_DELETE_WINDOW", self.onExitCloseThread)')
        self.master.protocol("WM_DELETE_WINDOW", self.onExitCloseAutoflipThread)

    def createWidgets(self):
        # Create the main frame that will hold a flashcard
        mainframe = tk.LabelFrame(self, **(self.mainframe_config))
        mainframe.pack(pady=20)
        self.widgets['mainframe'] = mainframe

        flipbtn = tk.Button(self, **(self.flp_btn_config))
        flipbtn.pack(side='top')
        self.widgets['flp_btn'] = flipbtn

        self.loadDeck()

        # Create the label widget that will represent the text for
        # all flashcards no matter whether front side or back side
        # and set its initial text to that of the first card in the deck
        flashcard_text = tk.Label(mainframe, **(self.flashcard_config))
        flashcard_text['text'] = f'{self.deck.cards["card_1"].frontside_labeltext}'
        flashcard_text.place(x=450, y=250, anchor='center')
        self.cur_card = self.deck.cards['card_1']
        self.widgets['label'] = flashcard_text

        jmp_end_btn = tk.Button(self, **(self.jmp_end_btn_config))
        jmp_end_btn.pack(side='right')
        self.widgets['jmp_end_btn'] = jmp_end_btn

        fwdbtn = tk.Button(self, **(self.fwd_btn_config))
        fwdbtn.pack(side='right')
        self.widgets['fwd_btn'] = fwdbtn

        jmp_start_btn = tk.Button(self, **(self.jmp_start_btn_config))
        jmp_start_btn.pack(side='left')
        self.widgets['jmp_start_btn'] = jmp_start_btn

        backbtn = tk.Button(self, **(self.bwd_btn_config))
        backbtn.pack(side='left')
        self.widgets['bwd_btn'] = backbtn

        goto_input = tk.Entry(self, **(self.goto_input_config))
        self.bind_class('Entry', '<Return>', self.gotoFlashcards)
        goto_input.pack(side='bottom')
        self.widgets['goto_input'] = goto_input

        if self.os != 'Linux':
            self.snd_btn_config['text'] = '  Play  '

        soundbtn = tk.Button(self, **(self.snd_btn_config))
        soundbtn.pack(side='bottom')
        self.widgets['snd_btn'] = soundbtn

        autoflip_chkbtn = tk.Checkbutton(self.master, **(self.autoflip_chkbtn_config))
        autoflip_chkbtn.place(relx=0.9, rely=0.1)
        self.widgets['autoflip_chkbtn'] = autoflip_chkbtn

        autowalk_chkbtn = tk.Checkbutton(self.master, **(self.autowalk_chkbtn_config))
        autowalk_chkbtn.place(relx=0.9, rely=0.15)
        self.widgets['autowalk_chkbtn'] = autowalk_chkbtn

        card_in_deck_pos = tk.Label(self.master, **self.card_in_deck_pos_config)
        card_in_deck_pos.place(relx=0.8, rely=0.9)
        self.widgets['card_in_deck_pos'] = card_in_deck_pos
        self.initCardCounter()

    def startAutoflipFunctionalityHandlerThreaded(self):
        # Easy dirty fix for having the same time
        # delay for the first card/click

        get_time_method = lambda: time.clock_gettime(time.CLOCK_REALTIME)

        if self.os == 'Windows' or self.os == 'Darwin':
            # Windows and MacOS don't have time.clock()
            # or time.clock_gettime()
            get_time_method = lambda: time.perf_counter()

        next_action = 'flip'
        next_time_diff = 4.0

        time_started = get_time_method()

        while self.autoflip.get() or self.autowalk.get():
            # Don't burn our CPU
            time.sleep(0.05)

            current_time = get_time_method()

            if current_time - time_started < next_time_diff:
                continue

            time_started = current_time

            if next_action == 'flip':
                self.flipFlashcard()
                if self.autowalk.get():
                    next_action = 'walk'
                    next_time_diff = self.fliptime
            elif next_action == 'walk':
                self.navigateFlashcards('forward')
                next_action = 'flip'
                next_time_diff = self.switchtime
        else:
            return False

    def autoflipEntryPoint(self):
        if self.autoflip.get() or self.autowalk.get():
            self.autoflip_thread = threading.Thread(target=self.startAutoflipFunctionalityHandlerThreaded)
            self.autoflip_thread.start()

        if self.autoflip.get():
            self.widgets['autowalk_chkbtn']['state'] = tk.DISABLED

        if self.autowalk.get():
            self.widgets['autoflip_chkbtn']['state'] = tk.DISABLED

        if not self.autoflip.get():
            self.widgets['autowalk_chkbtn']['state'] = tk.ACTIVE

        if not self.autowalk.get():
            self.widgets['autoflip_chkbtn']['state'] = tk.ACTIVE


def main():
    app_geometry = '1368x720'
    app_name = 'TPFlashcards'
    app_version = '0.2.2'
    app_bgcolor = '#303031'
    app_os = platform.system()

    args = constructAndGetArgs()

    csv_to_use = args.path_to_deck

    top_lvl_win = tk.Tk()

    flashcards_app = FlashcardsApp(top_lvl_win, app_geometry, app_name, app_version, app_bgcolor, csv_to_use, app_os, args)

    flashcards_app.mainloop()

if __name__ == '__main__':
    main()

