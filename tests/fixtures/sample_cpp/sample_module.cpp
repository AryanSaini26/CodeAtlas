#include <iostream>
#include <vector>
#include "utils.h"

namespace myapp {

/// A user entity
class User : public Entity, public Serializable {
public:
    User(const std::string& name, int age);
    ~User();

    /// Get the user's name
    std::string get_name() const;
    void set_name(const std::string& name);
    int get_age() const { return age_; }

    static User create(const std::string& name);

private:
    std::string name_;
    int age_;
};

/**
 * Abstract processor interface
 */
class IProcessor {
public:
    virtual ~IProcessor() = default;
    virtual void process(const User& user) = 0;
};

class UserProcessor : public IProcessor {
public:
    void process(const User& user) override;
};

enum class Color {
    Red,
    Green,
    Blue
};

struct Point {
    double x;
    double y;
    double distance_to(const Point& other) const;
};

template<typename T>
class Container {
public:
    void add(const T& item);
    T get(int index) const;
private:
    std::vector<T> items_;
};

const int MAX_USERS = 100;

using StringVec = std::vector<std::string>;

void free_function(int x, double y);

void implemented_function(int x) {
    auto user = User::create("test");
    user.set_name("hello");
}

namespace utils {
    int helper_func();
}

} // namespace myapp
