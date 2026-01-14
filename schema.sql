-- Create database if not exists
CREATE DATABASE IF NOT EXISTS online_lucky_draw;
USE online_lucky_draw;

-- Users table
CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(100) NOT NULL,
  email VARCHAR(100) UNIQUE NOT NULL,
  password VARCHAR(255) NOT NULL,
  role ENUM('user','admin') DEFAULT 'user'
);

-- Draws table
CREATE TABLE IF NOT EXISTS draws (
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(200) NOT NULL,
  description TEXT,
  draw_date DATE NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Participants Table (💯 CORRECTED)
CREATE TABLE IF NOT EXISTS participants (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  draw_id INT NOT NULL,
  name VARCHAR(100),
  email VARCHAR(100),
  phone VARCHAR(20),
  payment_method VARCHAR(50),
  bank_name VARCHAR(100),
  amount DECIMAL(10,2),
  joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (draw_id) REFERENCES draws(id) ON DELETE CASCADE,
  UNIQUE KEY unique_participation (user_id, draw_id)
);

-- Winners table
CREATE TABLE IF NOT EXISTS winners (
  id INT AUTO_INCREMENT PRIMARY KEY,
  draw_id INT NOT NULL,
  user_id INT NOT NULL,
  selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (draw_id) REFERENCES draws(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
