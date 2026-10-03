#include "tracker.hpp"

#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>

namespace {

using Options = std::map<std::string, std::string>;

void print_usage() {
    std::cout
        << "Cross-Language Expense Tracker (C++17)\n"
        << "Usage: expense_tracker [--data PATH] COMMAND [OPTIONS]\n\n"
        << "Commands:\n"
        << "  add --date YYYY-MM-DD --amount 12.34 --category Food --description Lunch\n"
        << "  list [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--category Food]\n"
        << "  search --query TEXT [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--category Food]\n"
        << "  summary [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--category Food]\n"
        << "  delete --id N\n"
        << "  help\n\n"
        << "Default data file: data/expenses.csv. Place --data before the command.\n"
        << "Quote values containing spaces. Categories match exactly; search ignores ASCII case.\n";
}

Options parse_options(int argc, char* argv[], int position,
                      const std::set<std::string>& allowed,
                      const std::set<std::string>& required) {
    Options options;
    while (position < argc) {
        const std::string flag = argv[position++];
        if (allowed.find(flag) == allowed.end()) {
            throw std::runtime_error("Unknown option: " + flag);
        }
        if (options.find(flag) != options.end()) {
            throw std::runtime_error("Duplicate option: " + flag);
        }
        if (position >= argc || std::string(argv[position]).rfind("--", 0) == 0) {
            throw std::runtime_error("Missing value for option: " + flag);
        }
        options.emplace(flag, argv[position++]);
    }
    for (const auto& flag : required) {
        if (options.find(flag) == options.end()) {
            throw std::runtime_error("Missing required option: " + flag);
        }
    }
    return options;
}

expense::Filters parse_filters(const Options& options) {
    expense::Filters filters;
    if (options.count("--start")) {
        filters.start = options.at("--start");
    }
    if (options.count("--end")) {
        filters.end = options.at("--end");
    }
    if (options.count("--category")) {
        filters.category = options.at("--category");
    }
    expense::validate_filters(filters);
    return filters;
}

void print_records(const std::vector<expense::Expense>& records) {
    std::cout << "ID | Date | Amount (USD) | Category | Description\n";
    if (records.empty()) {
        std::cout << "(no expenses)\n";
    }
    for (const auto& record : records) {
        std::cout << record.id << " | " << record.date << " | "
                  << expense::format_money(record.amount_cents) << " | "
                  << record.category << " | " << record.description << '\n';
    }
}

} // namespace

int main(int argc, char* argv[]) {
    try {
        int position = 1;
        std::filesystem::path file = "data/expenses.csv";
        if (position < argc && std::string(argv[position]) == "--data") {
            ++position;
            if (position >= argc || std::string(argv[position]).rfind("--", 0) == 0 ||
                std::string(argv[position]).empty()) {
                throw std::runtime_error("Missing value for option: --data");
            }
            file = argv[position++];
        }
        if (position == argc) {
            print_usage();
            return 0;
        }
        const std::string command = argv[position++];
        if (command == "help" || command == "--help" || command == "-h") {
            if (position != argc) {
                throw std::runtime_error("Help does not accept options.");
            }
            print_usage();
            return 0;
        }
        std::set<std::string> allowed;
        std::set<std::string> required;
        if (command == "add") {
            allowed = {"--date", "--amount", "--category", "--description"};
            required = allowed;
        } else if (command == "list" || command == "summary") {
            allowed = {"--start", "--end", "--category"};
        } else if (command == "search") {
            allowed = {"--start", "--end", "--category", "--query"};
            required = {"--query"};
        } else if (command == "delete") {
            allowed = {"--id"};
            required = allowed;
        } else {
            throw std::runtime_error("Unknown command: " + command);
        }
        const auto options = parse_options(argc, argv, position, allowed, required);
        auto tracker = expense::Tracker::load(file);
        if (command == "add") {
            const auto id = tracker.add(options.at("--date"), options.at("--amount"),
                                        options.at("--category"), options.at("--description"));
            tracker.save(file);
            std::cout << "Added expense #" << id << ".\n";
        } else if (command == "delete") {
            const auto id = expense::parse_id(options.at("--id"));
            tracker.erase(id);
            tracker.save(file);
            std::cout << "Deleted expense #" << id << ".\n";
        } else if (command == "summary") {
            const auto totals = tracker.summarize(parse_filters(options));
            std::cout << "Category | Total (USD)\n";
            for (const auto& entry : totals.by_category) {
                std::cout << entry.first << " | " << expense::format_money(entry.second) << '\n';
            }
            std::cout << "Overall | " << expense::format_money(totals.overall) << '\n';
        } else {
            const auto filters = parse_filters(options);
            if (command == "search") {
                print_records(tracker.select(filters, options.at("--query")));
            } else {
                print_records(tracker.select(filters));
            }
        }
        return 0;
    } catch (const std::exception& exception) {
        std::cerr << "Error: " << exception.what() << '\n';
        return 2;
    }
}
