#include "tracker.hpp"

#include <algorithm>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <limits>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <system_error>
#include <utility>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#endif

namespace expense {
namespace {

constexpr std::int64_t max_amount_cents = 99999999999LL;
constexpr std::size_t max_records = 100000;
constexpr std::size_t max_csv_line = 1024;
const std::vector<std::string> csv_header = {
    "id", "date", "amount_cents", "category", "description"
};

bool is_digit(char character) {
    return character >= '0' && character <= '9';
}

std::int64_t parse_digits(const std::string& value, std::int64_t maximum,
                          const std::string& field) {
    if (value.empty()) {
        throw std::runtime_error(field + " must contain decimal digits.");
    }
    std::int64_t result = 0;
    for (char character : value) {
        if (!is_digit(character)) {
            throw std::runtime_error(field + " must contain decimal digits.");
        }
        const int digit = character - '0';
        if (result > (maximum - digit) / 10) {
            throw std::runtime_error(field + " is out of range.");
        }
        result = result * 10 + digit;
    }
    return result;
}

std::int64_t checked_add(std::int64_t left, std::int64_t right) {
    if (right < 0 || left > std::numeric_limits<std::int64_t>::max() - right) {
        throw std::runtime_error("Expense total exceeds the supported range.");
    }
    return left + right;
}

std::string lowercase_ascii(std::string value) {
    for (char& character : value) {
        if (character >= 'A' && character <= 'Z') {
            character = static_cast<char>(character + ('a' - 'A'));
        }
    }
    return value;
}

// Parse RFC-style quoted fields, including commas and escaped double quotes.
// A record must fit on one line because text controls/newlines are prohibited.
std::vector<std::string> parse_csv_line(const std::string& line) {
    if (line.size() > max_csv_line) {
        throw std::runtime_error("CSV record is too long.");
    }
    std::vector<std::string> fields;
    std::size_t position = 0;
    while (true) {
        std::string field;
        if (position < line.size() && line[position] == '"') {
            ++position;
            bool closed = false;
            while (position < line.size()) {
                if (line[position] == '"') {
                    if (position + 1 < line.size() && line[position + 1] == '"') {
                        field.push_back('"');
                        position += 2;
                    } else {
                        ++position;
                        closed = true;
                        break;
                    }
                } else {
                    field.push_back(line[position++]);
                }
            }
            if (!closed || (position < line.size() && line[position] != ',')) {
                throw std::runtime_error("Malformed quoted CSV field.");
            }
        } else {
            while (position < line.size() && line[position] != ',') {
                if (line[position] == '"') {
                    throw std::runtime_error("Quote inside an unquoted CSV field.");
                }
                field.push_back(line[position++]);
            }
        }
        fields.push_back(std::move(field));
        if (fields.size() > csv_header.size()) {
            throw std::runtime_error("CSV record must contain exactly five fields.");
        }
        if (position == line.size()) {
            break;
        }
        ++position; // Consume the separating comma; preserve trailing empty fields.
    }
    if (fields.size() != csv_header.size()) {
        throw std::runtime_error("CSV record must contain exactly five fields.");
    }
    return fields;
}

std::string quote_csv(const std::string& value) {
    if (value.find_first_of(",\"") == std::string::npos) {
        return value;
    }
    std::string quoted = "\"";
    for (char character : value) {
        if (character == '"') {
            quoted.push_back('"');
        }
        quoted.push_back(character);
    }
    quoted.push_back('"');
    return quoted;
}

// The destructor removes a temporary file on every exceptional exit. Streams
// likewise close automatically through RAII, even when validation or I/O fails.
class TemporaryFile {
public:
    explicit TemporaryFile(std::filesystem::path path) : path_(std::move(path)) {}
    TemporaryFile(const TemporaryFile&) = delete;
    TemporaryFile& operator=(const TemporaryFile&) = delete;

    ~TemporaryFile() {
        if (active_) {
            std::error_code ignored;
            std::filesystem::remove(path_, ignored);
        }
    }

    const std::filesystem::path& path() const noexcept { return path_; }
    void committed() noexcept { active_ = false; }

private:
    std::filesystem::path path_;
    bool active_ = true;
};

std::filesystem::path temporary_path(const std::filesystem::path& target) {
    const auto stamp = std::chrono::high_resolution_clock::now().time_since_epoch().count();
    std::random_device random;
    for (int attempt = 0; attempt < 10; ++attempt) {
        const auto suffix = ".tmp-" + std::to_string(stamp) + "-" +
                            std::to_string(random());
        auto candidate = target;
        candidate += suffix;
        std::error_code error;
        const bool exists = std::filesystem::exists(candidate, error);
        if (error) {
            throw std::runtime_error("Cannot check temporary data path: " + error.message());
        }
        if (!exists) {
            return candidate;
        }
    }
    throw std::runtime_error("Cannot allocate a temporary data file.");
}

void replace_file(const std::filesystem::path& temporary,
                  const std::filesystem::path& target) {
#ifdef _WIN32
    // Windows rename does not overwrite existing files; use the native atomic
    // replacement operation. Both paths are in the same directory/filesystem.
    if (!MoveFileExW(temporary.c_str(), target.c_str(),
                     MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
        const auto error = static_cast<int>(GetLastError());
        throw std::runtime_error("Cannot replace data file: " +
                                 std::system_category().message(error));
    }
#else
    std::error_code error;
    std::filesystem::rename(temporary, target, error);
    if (error) {
        throw std::runtime_error("Cannot replace data file: " + error.message());
    }
#endif
}

} // namespace

void validate_date(const std::string& date) {
    const std::string error = "Date must be a valid calendar date in YYYY-MM-DD format.";
    if (date.size() != 10 || date[4] != '-' || date[7] != '-') {
        throw std::runtime_error(error);
    }
    for (std::size_t index = 0; index < date.size(); ++index) {
        if (index != 4 && index != 7 && !is_digit(date[index])) {
            throw std::runtime_error(error);
        }
    }
    const int year = static_cast<int>(parse_digits(date.substr(0, 4), 9999, "Year"));
    const int month = static_cast<int>(parse_digits(date.substr(5, 2), 99, "Month"));
    const int day = static_cast<int>(parse_digits(date.substr(8, 2), 99, "Day"));
    if (year == 0 || month < 1 || month > 12) {
        throw std::runtime_error(error);
    }
    const int days[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    int maximum = days[month - 1];
    if (month == 2 && (year % 400 == 0 || (year % 4 == 0 && year % 100 != 0))) {
        maximum = 29;
    }
    if (day < 1 || day > maximum) {
        throw std::runtime_error(error);
    }
}

std::string normalize_text(const std::string& value, std::size_t limit,
                           const std::string& field) {
    for (unsigned char character : value) {
        if (character < 32 || character > 126) {
            throw std::runtime_error(field + " must use printable ASCII characters.");
        }
    }
    const auto first = value.find_first_not_of(' ');
    if (first == std::string::npos) {
        throw std::runtime_error(field + " must not be empty.");
    }
    const auto last = value.find_last_not_of(' ');
    const std::string normalized = value.substr(first, last - first + 1);
    if (normalized.size() > limit) {
        throw std::runtime_error(field + " must be at most " + std::to_string(limit) +
                                 " characters.");
    }
    return normalized;
}

std::int64_t parse_amount(const std::string& amount) {
    const std::string error =
        "Amount must be positive, at most 999999999.99, with no more than two decimal places.";
    if (amount.empty()) {
        throw std::runtime_error(error);
    }
    const auto dot = amount.find('.');
    const std::string whole = amount.substr(0, dot);
    std::string fraction;
    if (dot != std::string::npos) {
        fraction = amount.substr(dot + 1);
        if (fraction.empty() || fraction.size() > 2) {
            throw std::runtime_error(error);
        }
    }
    if (whole.empty() || !std::all_of(whole.begin(), whole.end(), is_digit) ||
        !std::all_of(fraction.begin(), fraction.end(), is_digit)) {
        throw std::runtime_error(error);
    }
    const auto dollars = parse_digits(whole, 999999999, "Amount");
    std::int64_t cents = 0;
    if (!fraction.empty()) {
        cents = parse_digits(fraction, 99, "Amount");
        if (fraction.size() == 1) {
            cents *= 10;
        }
    }
    const auto result = dollars * 100 + cents;
    if (result <= 0 || result > max_amount_cents) {
        throw std::runtime_error(error);
    }
    return result;
}

std::int32_t parse_id(const std::string& value) {
    const auto id = parse_digits(value, std::numeric_limits<std::int32_t>::max(), "ID");
    if (id == 0) {
        throw std::runtime_error("ID must be positive.");
    }
    return static_cast<std::int32_t>(id);
}

std::string format_money(std::int64_t cents) {
    if (cents < 0) {
        throw std::runtime_error("Cannot format a negative expense amount.");
    }
    std::ostringstream output;
    output << '$' << cents / 100 << '.' << std::setfill('0') << std::setw(2) << cents % 100;
    return output.str();
}

void validate_filters(const Filters& filters) {
    if (filters.start) {
        validate_date(*filters.start);
    }
    if (filters.end) {
        validate_date(*filters.end);
    }
    if (filters.start && filters.end && *filters.start > *filters.end) {
        throw std::runtime_error("Start date must not be after end date.");
    }
    if (filters.category) {
        normalize_text(*filters.category, 40, "Category");
    }
}

Tracker Tracker::load(const std::filesystem::path& file) {
    if (file.empty() || file.filename().empty()) {
        throw std::runtime_error("Data path must name a file.");
    }
    std::error_code error;
    const bool exists = std::filesystem::exists(file, error);
    if (error) {
        throw std::runtime_error("Cannot access data file: " + error.message());
    }
    Tracker tracker;
    if (!exists) {
        return tracker;
    }
    if (!std::filesystem::is_regular_file(file, error) || error) {
        throw std::runtime_error("Data path must name a regular file.");
    }
    std::ifstream input(file, std::ios::binary);
    if (!input) {
        throw std::runtime_error("Cannot open data file for reading.");
    }
    std::string line;
    if (!std::getline(input, line)) {
        throw std::runtime_error("Malformed CSV: missing header.");
    }
    if (!line.empty() && line.back() == '\r') {
        line.pop_back();
    }
    if (parse_csv_line(line) != csv_header) {
        throw std::runtime_error("Malformed CSV: unexpected header.");
    }
    std::set<std::int32_t> identifiers;
    std::size_t line_number = 1;
    while (std::getline(input, line)) {
        ++line_number;
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        try {
            if (tracker.records_.size() >= max_records) {
                throw std::runtime_error("Data file exceeds the limit of 100000 expenses.");
            }
            const auto fields = parse_csv_line(line);
            const auto id = parse_id(fields[0]);
            if (!identifiers.insert(id).second) {
                throw std::runtime_error("Duplicate expense ID.");
            }
            validate_date(fields[1]);
            const auto cents = parse_digits(fields[2], max_amount_cents, "Amount in cents");
            if (cents == 0) {
                throw std::runtime_error("Amount in cents must be positive.");
            }
            const auto category = normalize_text(fields[3], 40, "Category");
            const auto description = normalize_text(fields[4], 200, "Description");
            if (category != fields[3] || description != fields[4]) {
                throw std::runtime_error("Stored category and description must be trimmed.");
            }
            tracker.records_.push_back({id, fields[1], cents, category, description});
        } catch (const std::runtime_error& exception) {
            throw std::runtime_error("Malformed CSV on line " + std::to_string(line_number) +
                                     ": " + exception.what());
        }
    }
    if (input.bad() || !input.eof()) {
        throw std::runtime_error("Cannot read data file completely.");
    }
    return tracker;
}

std::int32_t Tracker::add(const std::string& date, const std::string& amount,
                         const std::string& category, const std::string& description) {
    validate_date(date);
    const auto cents = parse_amount(amount);
    const auto normalized_category = normalize_text(category, 40, "Category");
    const auto normalized_description = normalize_text(description, 200, "Description");
    if (records_.size() >= max_records) {
        throw std::runtime_error("Cannot add more than 100000 expenses.");
    }
    std::int32_t highest = 0;
    for (const auto& record : records_) {
        highest = std::max(highest, record.id);
    }
    if (highest == std::numeric_limits<std::int32_t>::max()) {
        throw std::runtime_error("No expense IDs remain available.");
    }
    const auto id = static_cast<std::int32_t>(highest + 1);
    records_.push_back({id, date, cents, normalized_category, normalized_description});
    return id;
}

void Tracker::erase(std::int32_t id) {
    const auto record = std::find_if(records_.begin(), records_.end(),
                                     [id](const Expense& expense) { return expense.id == id; });
    if (record == records_.end()) {
        throw std::runtime_error("Expense ID was not found.");
    }
    records_.erase(record);
}

std::vector<Expense> Tracker::select(const Filters& filters,
                                    const std::optional<std::string>& query) const {
    validate_filters(filters);
    std::optional<std::string> normalized_category;
    if (filters.category) {
        normalized_category = normalize_text(*filters.category, 40, "Category");
    }
    std::optional<std::string> lowercase_query;
    if (query) {
        lowercase_query = lowercase_ascii(normalize_text(*query, 200, "Query"));
    }
    std::vector<Expense> selected;
    for (const auto& record : records_) {
        if ((filters.start && record.date < *filters.start) ||
            (filters.end && record.date > *filters.end) ||
            (normalized_category && record.category != *normalized_category)) {
            continue;
        }
        if (lowercase_query &&
            lowercase_ascii(record.category).find(*lowercase_query) == std::string::npos &&
            lowercase_ascii(record.description).find(*lowercase_query) == std::string::npos) {
            continue;
        }
        selected.push_back(record);
    }
    return selected;
}

Summary Tracker::summarize(const Filters& filters) const {
    Summary summary;
    for (const auto& record : select(filters)) {
        auto& category_total = summary.by_category[record.category];
        category_total = checked_add(category_total, record.amount_cents);
        summary.overall = checked_add(summary.overall, record.amount_cents);
    }
    return summary;
}

void Tracker::save(const std::filesystem::path& file) const {
    if (file.empty() || file.filename().empty()) {
        throw std::runtime_error("Data path must name a file.");
    }
    std::error_code error;
    const auto parent = file.parent_path();
    if (!parent.empty()) {
        std::filesystem::create_directories(parent, error);
        if (error) {
            throw std::runtime_error("Cannot create data directory: " + error.message());
        }
    }
    TemporaryFile temporary(temporary_path(file));
    {
        std::ofstream output(temporary.path(), std::ios::binary | std::ios::trunc);
        if (!output) {
            throw std::runtime_error("Cannot open temporary data file for writing.");
        }
        output << "id,date,amount_cents,category,description\n";
        for (const auto& record : records_) {
            output << record.id << ',' << record.date << ',' << record.amount_cents << ','
                   << quote_csv(record.category) << ',' << quote_csv(record.description) << '\n';
        }
        output.flush();
        if (!output) {
            throw std::runtime_error("Cannot write complete expense data.");
        }
        output.close();
        if (!output) {
            throw std::runtime_error("Cannot close temporary data file.");
        }
    }
    replace_file(temporary.path(), file);
    temporary.committed();
}

} // namespace expense
