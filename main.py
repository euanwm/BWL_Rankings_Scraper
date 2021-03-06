#!/usr/bin/env python
import requests
import csv
from bs4 import BeautifulSoup
from entry_dataclass import LiftEntry
from filtered_data.data_tools import dump_to_csv
from scraper_tools import get_table_rows, get_table_headers, stripper
from statistics import mean, median
from magic_things import MADE, ENTRY_LENGTH
from static_tools import distribute_data, convert_to_csv_list, check_and_fix_entry, sort_lift_order
from time import time


def setup_db():
    scraper.create_meets_index_db()
    scraper.check_index_db()
    scraper.create_results_db()
    if not scraper.check_results_db():
        raise RuntimeError("INCONSISTENT RESULTS DATABASE\t-\tDouble check results_db")


class DatabaseScraper:
    def __init__(self):
        self.BROWSER_SESSION = requests.Session()
        self.EVENT_INDEX = "https://bwl.sport80.com/event_results?id_ranking=8"
        self.RESULTS_DB: list = []

    def update_all_db(self):
        self.create_meets_index_db()
        self.check_index_db()
        self.create_results_db()
        self.check_results_db()

    @staticmethod
    def strip_result_table(page_text: str, table_id="ranking-matches"):
        soup = BeautifulSoup(page_text, "html.parser")
        result_table = soup.find("table", id=table_id)
        # table_headers = get_table_headers(result_table)
        table_rows = get_table_rows(result_table)
        # table_rows.insert(0, table_headers)
        return table_rows

    def strip_index_table(self):
        index_page = self.BROWSER_SESSION.get(self.EVENT_INDEX)
        result_table_id = "ranking-matches-resources"
        soup = BeautifulSoup(index_page.text, "html.parser")
        result_table = soup.find("table", id=result_table_id)
        table_headers = get_table_headers(result_table)
        table_rows = get_table_rows(result_table, True)
        table_rows.insert(0, table_headers)
        # Todo - make this shit modular...and the strip_results_table thing
        parsed_table = table_rows
        return parsed_table

    def get_event_result(self, event_id: int):
        event_page = self.BROWSER_SESSION.get(f"{self.EVENT_INDEX}&resource={event_id}")
        return self.strip_result_table(event_page.text)

    def create_meets_index_db(self):
        """
        Will need to make an update version of this to stop pulling through all the shit again
        """
        meet_options = self.strip_index_table()
        with open("data/meets_index_db.csv", "w", newline='') as csv_file:
            csvwrite = csv.writer(csv_file)
            for meets in meet_options:
                csvwrite.writerow(meets)

    def create_results_db(self):
        event_id_list = []
        with open("data/meets_index_db.csv", "r") as index_file:
            index_csv = csv.reader(index_file)
            next(index_file)
            for rows in index_csv:
                event_id_list.append(int(rows[4]))
        for ids in event_id_list:
            self.write_results(ids)

    def write_results(self, event_id: int):
        with open("data/results_db.csv", "a", newline='') as results_db:
            csv_write = csv.writer(results_db)
            for rows in self.get_event_result(event_id):
                csv_write.writerow(rows)

    def check_results_db(self):
        """
        Runs through the results DB to make sure lines add up right
        Expected entry length is 14.
        """
        results_db = self.load_results_db()
        bad_entries = []
        for lines in results_db:
            if len(lines) != ENTRY_LENGTH:
                bad_entries.append(lines)
        return False if len(bad_entries) != 0 else True

    def single_lifter_comps_one_year(self, year, results_limit):
        self.repeat_lifter: dict = {}
        total_lifts_yr: int = 0
        results_db = self.load_results_db()
        for entry in results_db:
            if year in entry.date:
                total_lifts_yr += 1
                self.repeat_lifter_count(entry.lifter_name)
        self.repeat_lifter = dict(sorted(self.repeat_lifter.items(), key=lambda x: x[1], reverse=True))
        print(f"Lifters with most competitions in {year}".upper())
        print("--------------------------------------")

        for index, (lifter, comp_n) in enumerate(self.repeat_lifter.items()):
            print(f"{lifter}:  {comp_n}")
            self.single_lifter_results(lifter, year)
            if index == results_limit - 1:
                break

    def filter_by_year(self, results_db: list, year: str) -> list:
        filtered_db = []
        for line in results_db:
            if year in line[1]:
                filtered_db.append(line)
        return filtered_db

    def top_totals(self, year: str = None):
        results_db = self.load_results_db()
        if year:
            results_db = self.filter_by_year(results_db, year)
        top_lifts = {}
        for entry in results_db:
            if entry.lifter_name() not in top_lifts and entry.total_kg():
                top_lifts[entry.lifter_name()] = entry.total_kg()
            elif entry.lifter_name() in top_lifts and entry.total_kg() > top_lifts[entry.lifter_name()]:
                top_lifts[entry.lifter_name()] = entry.total_kg()

        sorted_lifts = (sorted(top_lifts.items(), key=lambda x: x[1], reverse=True))
        # return [(key, value) for key, value in top_lifts.items()]
        print(sorted_lifts)
        self.bubble_sort(sorted_lifts)

    def bubble_sort(self, lifts_list: list):
        for _ in range(3):
            new_ele = 1
            new_lis_len = len(lifts_list)
            for k in range(0, new_lis_len):
                for l in range(0, new_lis_len - k - 1):
                    if lifts_list[l][new_ele] > lifts_list[l + 1][new_ele]:
                        new_tem = lifts_list[l]
                        lifts_list[l] = lifts_list[l + 1]
                        lifts_list[l + 1] = new_tem
            print(lifts_list[::-1])

    def load_results_db(self) -> list:
        results_db = []
        with open("data/results_db.csv", "r") as index_file:
            index_csv = csv.reader(index_file)
            for row in index_csv:
                checked_row = check_and_fix_entry(row)
                results_db.append(LiftEntry(checked_row))
        return results_db

    def repeat_lifter_count(self, lifter_name: str):
        if lifter_name not in self.repeat_lifter:
            self.repeat_lifter[lifter_name] = 1
        elif lifter_name in self.repeat_lifter:
            self.repeat_lifter[lifter_name] += 1

    def check_index_db(self):
        """
        Runs through the results DB to make sure lines add up right
        """
        result_object = []
        with open("data/meets_index_db.csv", "r") as index_file:
            index_csv = csv.reader(index_file)
            for rows in index_csv:
                if len(rows) != 5:
                    print(rows)

    def single_lifter_results(self, lifter_name: str, year: list):
        results_db: list = self.load_results_db()
        lifter_results: dict = {}
        year = sorted(year, reverse=False)
        sinclair: list = [lifter_name]
        for entry in results_db:
            for yr in year:
                if yr == entry.year and lifter_name in entry.lifter_name:
                    sinclair.append(entry.sinclair)
        #lifter_results[lifter_name] = sinclair
        return sinclair
        # lifter_filename = self.gen_filename(lifter_name, year)
        # self.write_lifter_db(lifter_filename, lifter_results)

    def write_lifter_db(self, filename: str, line_data: list):
        header = ['DATE', 'MADE SNATCH (%)', 'MADE C&J (%)', 'COMBINED MADE LIFT (%)', 'BEST SNATCH',
                  'BEST C&J', 'TOTAL', 'SINCLAIR']
        with open(f"lifter_data/{filename}.csv", "w", newline='') as results_db:
            csv_write = csv.writer(results_db)
            csv_write.writerow(header)
            for rows in line_data[::-1]:
                csv_write.writerow(rows)

    def gen_filename(self, lifter_name, year):
        lifter = lifter_name.replace(' ', '_')
        return f"{lifter}_{year}"

    def second_snatches(self):
        results_db: list = self.load_results_db()
        made_list = []
        percentages = []
        year = '2021'
        for entry in results_db:
            try:
                if year in entry.date and 'made' in entry.first_snatch_jump():
                    made_list.append(entry)
            except TypeError:
                print(entry.full_entry)
        for entry in made_list:
            percentages.append(entry.first_snatch_jump()[1])
        max_percentage = max(percentages)
        print(f"Median jump: {median(percentages)}\n"
              f"Average jump: {mean(percentages)}\n"
              f"Largest jump: {max_percentage}")
        for entry in made_list:
            if (entry.first_snatch_jump()[1]) == max_percentage:
                print(entry.full_entry)
        attempt_dist = distribute_data(percentages)
        # dump_to_csv("second_snatch_attempts", convert_to_csv_list(attempt_dist))

    def third_snatches(self):
        results_db: list = self.load_results_db()
        made_list = []
        percentages = []
        year = '2021'
        for entry in results_db:
            try:
                if year in entry.date and MADE in entry.second_snatch_jump():
                    made_list.append(entry)
            except TypeError:
                print(entry.full_entry)
        for entry in made_list:
            percentages.append(entry.second_snatch_jump()[1])
        max_percentage = max(percentages)
        print(f"Median jump: {median(percentages)}\n"
              f"Average jump: {mean(percentages)}\n"
              f"Largest jump: {max_percentage}")
        for entry in made_list:
            if (entry.second_snatch_jump()[1]) == max_percentage:
                print(entry.full_entry)
        attempt_dist = distribute_data(percentages)
        # dump_to_csv("third_snatch_attempts", convert_to_csv_list(attempt_dist))

    def second_cjs(self):
        results_db: list = self.load_results_db()
        made_list = []
        percentages = []
        year = '2021'
        for entry in results_db:
            try:
                if year in entry.date and 'made' in entry.first_cj_jump():
                    made_list.append(entry)
            except TypeError:
                print(entry.full_entry)
        for entry in made_list:
            percentages.append(entry.first_cj_jump()[1])
        max_percentage = max(percentages)
        print(f"Median jump: {median(percentages)}\n"
              f"Average jump: {mean(percentages)}\n"
              f"Largest jump: {max_percentage}")
        for entry in made_list:
            if (entry.first_cj_jump()[1]) == max_percentage:
                print(entry.full_entry)
        attempt_dist = distribute_data(percentages)
        # dump_to_csv("second_cj_attempts", convert_to_csv_list(attempt_dist))

    def third_cjs(self):
        results_db: list = self.load_results_db()
        made_list = []
        percentages = []
        year = '2021'
        for entry in results_db:
            try:
                if year in entry.date and MADE in entry.second_cj_jump():
                    made_list.append(entry)
            except TypeError:
                print(entry.full_entry)
        for entry in made_list:
            percentages.append(entry.second_cj_jump()[1])
        max_percentage = max(percentages)
        print(f"Median jump: {median(percentages)}\n"
              f"Average jump: {mean(percentages)}\n"
              f"Largest jump: {max_percentage}")
        for entry in made_list:
            if (entry.second_cj_jump()[1]) == max_percentage:
                print(entry.full_entry)
        attempt_dist = distribute_data(percentages)
        # dump_to_csv("third_cj_attempts", convert_to_csv_list(attempt_dist))

    def top_10(self, year: int = None, gender: str = None):
        results_db: list = self.load_results_db()
        big_list: list = []
        for entry in results_db:
            if year == entry.year and gender == entry.lifter_gender:
                big_list.append([entry.lifter_name, entry.sinclair])
        sorted_big_list = sort_lift_order(big_list, reverse=True)

        for _ in range(2):
            for n_1, x in enumerate(sorted_big_list):
                for n_2, y in enumerate(sorted_big_list):
                    if x[0] == y[0] and x[1] >= y[1] and n_1 != n_2:
                        big_list.pop(n_2)
        print(f"Top 10 in {year}")
        for x in range(10):
            print(sorted_big_list[x])
        dump_to_csv(f"top10_women_{year}", sorted_big_list[:10:])

    def historical_top_10(self, years: list):
        for year in years:
            self.top_10(year, "Women's")

    def best_lifter_sinclair(self, name: str, year: int):
        pass

if __name__ == '__main__':
    scraper = DatabaseScraper()
    # scraper.second_snatches()
    # scraper.third_snatches()
    # scraper.second_cjs()
    # scraper.third_cjs()
    # scraper.single_lifter_comps_one_year('2021', 10)
    # scraper.single_lifter_results()
    # scraper.load_results_db()
    # lifts = scraper.top_totals('2021')
    # dump_to_csv("top_totals", lifts)
    #scraper.top_10(2021, "Men's")
    #scraper.top_10(2021, "Women's")
    scraper.historical_top_10([2017,2018,2019,2020,2021])