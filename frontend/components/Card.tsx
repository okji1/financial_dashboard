'use client'

import React from 'react';

interface CardProps {
  title: string;
  children: React.ReactNode;
}

const Card: React.FC<CardProps> = ({ title, children }) => {
  return (
    <div className="bg-white dark:bg-gray-800 shadow-lg rounded-lg p-6 mb-6">
      <h2 className="text-2xl font-bold mb-4 text-gray-900 dark:text-white">{title}</h2>
      <div>{children}</div>
    </div>
  );
};

export default Card;
