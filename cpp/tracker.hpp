#ifndef EXPENSE_TRACKER_HPP
#define EXPENSE_TRACKER_HPP

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace expense {

// Value ownership keeps every record tied to its containing vector. There are
// no owning raw pointers and no manual new/delete operations.
struct Expense {
    std::int32_t id;
    std::string date;
    std::int64_t amount_cents;
    std::string category;
    std::string description;
};

struct Filters {
    std::optional<std::string> start;
    std::optional<std::string> end;
    std::optional<std::string> category;
};

struct Summary {
    // std::map keeps the CLI's category order stable and lexicographic.
    std::map<std::string, std::int64_t> by_category;
    std::int64_t overall = 0;
};

void validate_date(const std::string& date);
void validate_filters(const Filters& filters);
std::string normalize_text(const std::string& value, std::size_t limit,
                           const std::string& field);
std::int64_t parse_amount(const std::string& amount);
std::int32_t parse_id(const std::string& value);
std::string format_money(std::int64_t cents);

class Tracker {
public:
    static Tracker load(const std::filesystem::path& file);

    std::int32_t add(const std::string& date, const std::string& amount,
                     const std::string& category, const std::string& description);
    void erase(std::int32_t id);
    std::vector<Expense> select(const Filters& filters,
                                const std::optional<std::string>& query = std::nullopt) const;
    Summary summarize(const Filters& filters) const;
    void save(const std::filesystem::path& file) const;

    const std::vector<Expense>& records() const noexcept { return records_; }

private:
    std::vector<Expense> records_;
};

} // namespace expense

#endif
