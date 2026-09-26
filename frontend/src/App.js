import React, { useState, useRef, useEffect } from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import axios from "axios";
import "./App.css";
import anatomyLogo from "./assets/Logo2.JPG";

/**
 * =========================================================
 * Environment Configuration
 * =========================================================
 */
const API_BASE_URL = process.env.REACT_APP_API_URL || "";

/**
 * =========================================================
 * Chatbot Page
 * =========================================================
 */
function ChatbotPage() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userEmail, setUserEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showLogin, setShowLogin] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /**
   * ------------------------
   * Authentication
   * ------------------------
   */
  const handleLogin = async () => {
    try {
      const response = await axios.post(
        `${API_BASE_URL}/api/login`,
        { email: userEmail, password },
        { withCredentials: true }
      );

      if (response.data.success) {
        setIsLoggedIn(true);
        setShowLogin(false);
      } else {
        alert(response.data.message || "Login failed.");
      }
    } catch (error) {
      console.error("Login error:", error);
      alert("Login failed. Please check your credentials.");
    }
  };

  const handleSignup = async () => {
    try {
      const response = await axios.post(`${API_BASE_URL}/api/signup`, {
        email: userEmail,
        password,
      });

      if (response.data.success) {
        alert("Signup successful! Please log in.");
        setShowLogin(true);
      } else {
        alert(response.data.message || "Signup failed.");
      }
    } catch (error) {
      console.error("Signup error:", error);
      alert("Signup failed. Please try again.");
    }
  };

  const handleLogout = () => {
    setIsLoggedIn(false);
    setMessages([]);
    setUserEmail("");
    setPassword("");
    setShowLogin(true);
  };

  /**
   * ------------------------
   * Chat
   * ------------------------
   */
  const handleAsk = async () => {
    if (!question.trim()) return;

    const userQuestion = question;
    setQuestion("");
    setMessages((prev) => [...prev, { sender: "user", text: userQuestion }]);
    setIsLoading(true);

    try {
      // Get last 5 messages for conversation context
      const recentMessages = messages.slice(-5).map(msg => ({
        role: msg.sender === "user" ? "user" : "assistant",
        content: msg.text
      }));

      const response = await axios.post(`${API_BASE_URL}/api/chat`, {
        question: userQuestion,
        userEmail: isLoggedIn ? userEmail : "anonymous",
        conversationHistory: recentMessages,
      });

      setMessages((prev) => [
        ...prev,
        { sender: "bot", text: response.data.answer },
      ]);
    } catch (error) {
      console.error("Chat error:", error);
      setMessages((prev) => [
        ...prev,
        {
          sender: "bot",
          text: "Error retrieving response. Please try again.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  };

  /**
   * ------------------------
   * UI
   * ------------------------
   */
  return (
    <div className="app-wrapper">
      {/* Background decoration */}
      <div className="bg-decoration">
        <div className="bg-circle bg-circle-1"></div>
        <div className="bg-circle bg-circle-2"></div>
        <div className="bg-circle bg-circle-3"></div>
      </div>

      <div className="main-container">
        {/* Header */}
        <header className="app-header">
          <div className="logo">
            <img
              src={anatomyLogo}
              alt="Anatomy Assistant Logo"
              className="logo-icon"
            />
            <span className="logo-text">Anatomy Assistant</span>
          </div>
          {isLoggedIn && (
            <div className="user-info">
              <span className="user-email">{userEmail}</span>
              <button className="logout-btn" onClick={handleLogout}>
                Logout
              </button>
            </div>
          )}
        </header>

        {!isLoggedIn ? (
          /* Login/Signup Form */
          <div className="auth-container">
            <div className="auth-card">
              <div className="auth-header">
                <h1>Welcome Back</h1>
                <p>Sign in to continue your anatomy studies</p>
              </div>

              <div className="auth-tabs">
                <button
                  className={`auth-tab ${showLogin ? "active" : ""}`}
                  onClick={() => setShowLogin(true)}
                >
                  Login
                </button>
                <button
                  className={`auth-tab ${!showLogin ? "active" : ""}`}
                  onClick={() => setShowLogin(false)}
                >
                  Sign Up
                </button>
              </div>

              <div className="auth-form">
                <div className="input-group">
                  <label htmlFor="email">Email</label>
                  <input
                    id="email"
                    type="email"
                    placeholder="you@university.edu"
                    value={userEmail}
                    onChange={(e) => setUserEmail(e.target.value)}
                  />
                </div>

                <div className="input-group">
                  <label htmlFor="password">Password</label>
                  <input
                    id="password"
                    type="password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>

                <button
                  className="auth-submit"
                  onClick={showLogin ? handleLogin : handleSignup}
                >
                  {showLogin ? "Sign In" : "Create Account"}
                </button>
              </div>
            </div>
          </div>
        ) : (
          /* Chat Interface */
          <div className="chat-wrapper">
            <div className="chat-card">
              {/* Chat Header */}
              <div className="chat-header">
                <h2>Anatomy Assistant</h2>
                <p>Ask questions about anatomy videos and documents</p>
              </div>

              {/* Messages Area */}
              <div className="messages-container">
                {messages.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-icon">
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.5"
                      >
                        <path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                      </svg>
                    </div>
                    <h3>Start a Conversation</h3>
                    <p>
                      Ask me about anatomy topics, video timestamps, or concepts
                      from your course materials.
                    </p>
                    <div className="suggested-questions">
                      <button
                        onClick={() =>
                          setQuestion(
                            "Where in the video can I see the coracobrachialis muscle?"
                          )
                        }
                      >
                        📍 Where is the coracobrachialis muscle?
                      </button>
                      <button
                        onClick={() =>
                          setQuestion(
                            "What does the musculocutaneous nerve innervate?"
                          )
                        }
                      >
                        🔬 Musculocutaneous nerve innervation?
                      </button>
                      <button
                        onClick={() =>
                          setQuestion("Explain the cubital fossa boundaries")
                        }
                      >
                        📚 Cubital fossa boundaries?
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="messages-list">
                    {messages.map((message, index) => (
                      <div
                        key={index}
                        className={`message ${
                          message.sender === "user" ? "user" : "bot"
                        }`}
                      >
                        {message.sender === "bot" && (
                          <div className="message-avatar">
                            <img
                              src={anatomyLogo}
                              alt="Anatomy Assistant"
                              className="avatar-logo"
                            />
                          </div>
                        )}
                        <div className="message-content">
                          <p>{message.text}</p>
                        </div>
                      </div>
                    ))}
                    {isLoading && (
                      <div className="message bot">
                        <div className="message-avatar">
                          <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                          >
                            <path d="M12 2L2 7l10 5 10-5-10-5z" />
                            <path d="M2 17l10 5 10-5" />
                            <path d="M2 12l10 5 10-5" />
                          </svg>
                        </div>
                        <div className="message-content typing">
                          <span></span>
                          <span></span>
                          <span></span>
                        </div>
                      </div>
                    )}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>

              {/* Input Area */}
              <div className="input-area">
                <div className="input-wrapper">
                  <input
                    type="text"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="Ask about anatomy topics or video timestamps..."
                    disabled={isLoading}
                  />
                  <button
                    className="send-btn"
                    onClick={handleAsk}
                    disabled={isLoading || !question.trim()}
                  >
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
                    </svg>
                  </button>
                </div>
                <p className="disclaimer">
                  AI-generated answers may contain errors. Always verify with
                  your instructor and course materials.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
      <footer className="app-footer">
        <p>© 2024–2026 University of Pittsburgh — HEILab. All rights reserved.</p>
      </footer>
    </div>
  );
}

/**
 * =========================================================
 * App Router
 * =========================================================
 */
function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<ChatbotPage />} />
      </Routes>
    </Router>
  );
}

export default App;