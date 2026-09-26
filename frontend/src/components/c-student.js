import React, { useState, useEffect } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import "../index.css";

const Student = () => {
  const [userEmail, setUserEmail] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const API_BASE_URL = process.env.REACT_APP_API_URL;

  useEffect(() => {
    const fetchSession = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/session`, {
          withCredentials: true,
        });

        if (
          response.data.user_email &&
          response.data.user_email !== "No session email"
        ) {
          setUserEmail(response.data.user_email);
        } else {
          navigate("/login");
        }
      } catch (error) {
        console.error("Error fetching session:", error);
        navigate("/login");
      } finally {
        setLoading(false);
      }
    };

    fetchSession();
  }, [navigate, API_BASE_URL]);

  if (loading) {
    return <div>Loading session...</div>;
  }

  return (
    <div className="container">
      <h1>Human Anatomy Chatbot</h1>
      <p>{userEmail ? `✅ Logged in as: ${userEmail}` : "⚠️ Not logged in"}</p>
    </div>
  );
};

export default Student;
