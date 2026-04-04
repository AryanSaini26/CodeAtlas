using System;
using System.Collections.Generic;
using System.Linq;

namespace MyApp.Models
{
    /// <summary>
    /// Represents a user in the system.
    /// </summary>
    public class User : BaseEntity, ISerializable
    {
        public string Name { get; set; }
        public int Age { get; set; }

        public User(string name, int age)
        {
            Name = name;
            Age = age;
        }

        /// <summary>
        /// Validates the user data.
        /// </summary>
        public bool Validate()
        {
            return !string.IsNullOrEmpty(Name) && Age > 0;
        }

        public static User Create(string name)
        {
            return new User(name, 0);
        }

        private void LogAction(string action)
        {
            Console.WriteLine(action);
        }
    }

    public interface IProcessor<T>
    {
        void Process(T item);
        bool CanProcess(T item);
    }

    public class UserProcessor : IProcessor<User>
    {
        public void Process(User item)
        {
            item.Validate();
        }

        public bool CanProcess(User item)
        {
            return item != null;
        }
    }

    public enum UserRole
    {
        Admin,
        Editor,
        Viewer
    }

    public struct Point
    {
        public double X;
        public double Y;

        public double DistanceTo(Point other)
        {
            var dx = X - other.X;
            var dy = Y - other.Y;
            return Math.Sqrt(dx * dx + dy * dy);
        }
    }

    public record UserDto(string Name, int Age);

    public abstract class Repository<T> where T : class
    {
        public abstract T GetById(int id);
        public abstract void Save(T entity);
    }

    public static class Extensions
    {
        public static string ToUpperCase(this string s)
        {
            return s.ToUpper();
        }
    }
}
