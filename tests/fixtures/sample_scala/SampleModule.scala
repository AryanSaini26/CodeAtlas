import scala.collection.mutable.ListBuffer
import java.io.File

val MAX_SIZE = 100
val appName = "CodeAtlas"

// Defines greeting behavior
trait Greeter {
  def greet(): String
}

// Base entity
trait Entity {
  def id: Long
}

/**
 * Manages user operations
 */
class UserService extends Entity with Greeter {
  // Creates a new user
  def createUser(name: String): String = {
    validate(name)
    format(name)
  }

  override def greet(): String = "Hello"

  def id: Long = 0L
}

// Concrete user class
class AdminService(role: String) extends UserService {
  def promote(user: String): Unit = {
    update(user)
  }
}

object Config {
  // Load configuration
  def load(): String = {
    readConfig()
  }
}

def processAll(items: List[String]): Unit = {
  items.foreach(doWork)
}
