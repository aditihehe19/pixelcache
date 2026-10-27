// Minimal JSON reader for benchmark configuration files (objects, arrays,
// strings without unicode escapes beyond \uXXXX passthrough, numbers, bools,
// null). Header-only, no dependencies; throws std::runtime_error on errors.
#pragma once

#include <cctype>
#include <cstdlib>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace cachevision {
namespace json {

struct Value {
    enum Type { Null, Bool, Number, String, Array, Object } type = Null;
    bool b = false;
    double num = 0.0;
    std::string str;
    std::vector<Value> arr;
    std::map<std::string, Value> obj;

    bool has(const std::string& k) const { return type == Object && obj.count(k) != 0; }
    const Value& operator[](const std::string& k) const {
        auto it = obj.find(k);
        if (type != Object || it == obj.end()) throw std::runtime_error("json: missing key '" + k + "'");
        return it->second;
    }
    double as_number() const {
        if (type != Number) throw std::runtime_error("json: expected number");
        return num;
    }
    const std::string& as_string() const {
        if (type != String) throw std::runtime_error("json: expected string");
        return str;
    }
};

class Parser {
public:
    explicit Parser(const std::string& text) : s_(text) {}
    Value parse() {
        Value v = value();
        ws();
        if (i_ != s_.size()) fail("trailing characters");
        return v;
    }

private:
    [[noreturn]] void fail(const std::string& what) {
        throw std::runtime_error("json: " + what + " at offset " + std::to_string(i_));
    }
    void ws() {
        while (i_ < s_.size()) {
            if (std::isspace(static_cast<unsigned char>(s_[i_]))) ++i_;
            else if (s_.compare(i_, 2, "//") == 0) {  // tolerate line comments
                while (i_ < s_.size() && s_[i_] != '\n') ++i_;
            } else break;
        }
    }
    bool eat(char c) {
        ws();
        if (i_ < s_.size() && s_[i_] == c) { ++i_; return true; }
        return false;
    }
    void expect(char c) {
        if (!eat(c)) fail(std::string("expected '") + c + "'");
    }
    Value value() {
        ws();
        if (i_ >= s_.size()) fail("unexpected end");
        const char c = s_[i_];
        Value v;
        if (c == '{') {
            ++i_;
            v.type = Value::Object;
            if (eat('}')) return v;
            do {
                ws();
                Value k = string_value();
                expect(':');
                v.obj[k.str] = value();
            } while (eat(','));
            expect('}');
        } else if (c == '[') {
            ++i_;
            v.type = Value::Array;
            if (eat(']')) return v;
            do v.arr.push_back(value());
            while (eat(','));
            expect(']');
        } else if (c == '"') {
            v = string_value();
        } else if (s_.compare(i_, 4, "true") == 0) {
            i_ += 4; v.type = Value::Bool; v.b = true;
        } else if (s_.compare(i_, 5, "false") == 0) {
            i_ += 5; v.type = Value::Bool;
        } else if (s_.compare(i_, 4, "null") == 0) {
            i_ += 4;
        } else {
            const char* begin = s_.c_str() + i_;
            char* end = nullptr;
            v.num = std::strtod(begin, &end);
            if (end == begin) fail("invalid value");
            v.type = Value::Number;
            i_ += std::size_t(end - begin);
        }
        return v;
    }
    Value string_value() {
        if (i_ >= s_.size() || s_[i_] != '"') fail("expected string");
        ++i_;
        Value v;
        v.type = Value::String;
        while (i_ < s_.size() && s_[i_] != '"') {
            char c = s_[i_++];
            if (c == '\\' && i_ < s_.size()) {
                const char e = s_[i_++];
                switch (e) {
                    case 'n': c = '\n'; break;
                    case 't': c = '\t'; break;
                    case 'u': v.str += "\\u"; continue;
                    default: c = e;
                }
            }
            v.str += c;
        }
        if (i_ >= s_.size()) fail("unterminated string");
        ++i_;
        return v;
    }
    const std::string& s_;
    std::size_t i_ = 0;
};

inline Value parse(const std::string& text) { return Parser(text).parse(); }

}  // namespace json
}  // namespace cachevision
