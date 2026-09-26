import React, { useState } from "react";
import axios from "axios";
import { useNavigate, Link } from "react-router-dom";
import "../index.css";

const Login = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const API_BASE_URL = process.env.REACT_APP_API_URL;

  const handleLogin = async () => {
    if (!username || !password) {
      setError("Username and password are required.");
      return;
    }

    try {
      const response = await axios.post(
        `${API_BASE_URL}/login`,
        { username, password },
        { withCredentials: true }
      );
      console.log("Login Response:", response);

      const sessionResponse = await axios.get(`${API_BASE_URL}/session`, {
        withCredentials: true,
      });
      console.log("Session Response:", sessionResponse);

      if (sessionResponse.status === 200) {
        navigate("/student");
      } else {
        setError("Session not found, please try logging in again.");
      }
    } catch (err) {
      setError("Invalid username or password.");
    }
  };

  return (
    <div className="container">
      <div className="login-panel card">
        <h1>Login</h1>
        {error && <p className="message error">{error}</p>}
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button onClick={handleLogin}>Login</button>
        <p>
          Don't have an account? <Link to="/register">Register here</Link>
        </p>
      </div>
    </div>
  );
};

export default Login;
