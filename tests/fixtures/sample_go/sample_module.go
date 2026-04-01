package animals

import (
	"fmt"
	"strings"
)

const MaxAge = 100

var DefaultName = "Unknown"

// Animal defines the behavior of an animal.
type Animal interface {
	Speak() string
}

// Dog is a pet that can speak and fetch.
type Dog struct {
	Name string
	Age  int
}

// Speak returns the dog's greeting.
func (d *Dog) Speak() string {
	return fmt.Sprintf("Woof! I am %s", d.Name)
}

// Fetch retrieves an item.
func (d *Dog) Fetch(item string) string {
	result := strings.ToUpper(item)
	return fmt.Sprintf("%s fetches %s", d.Name, result)
}

// NewDog creates a new Dog instance.
func NewDog(name string, age int) *Dog {
	return &Dog{Name: name, Age: age}
}

// Greet returns a greeting for the given name.
func Greet(name string) string {
	return fmt.Sprintf("Hello, %s", name)
}

// Server holds config for a network server.
type Server struct {
	host string
	port int
}

// Start boots the server.
func (s *Server) Start() error {
	addr := fmt.Sprintf("%s:%d", s.host, s.port)
	fmt.Println(addr)
	return nil
}

type StringAlias = string
