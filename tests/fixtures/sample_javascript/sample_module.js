import { readFile } from 'fs';
import path from 'path';

const MAX_RETRIES = 3;

/**
 * Manages user data
 */
class UserService {
  // Creates a new service
  constructor(db) {
    this.db = db;
  }

  /** Fetch a user by id */
  async getUser(id) {
    const data = await fetch(id);
    return parse(data);
  }

  static create(db) {
    return new UserService(db);
  }
}

class AdminService extends UserService {
  promote(user) {
    return update(user);
  }
}

// Process a list of items
function processItems(items) {
  return items.map(transform);
}

const helper = (x) => compute(x);

const greet = function(name) {
  return format(name);
};

export { UserService, processItems };
